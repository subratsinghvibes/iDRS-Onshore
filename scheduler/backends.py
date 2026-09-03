"""
LDAP Authentication Backend for ONGC IDRS
==========================================

Authenticates users against ONGC Active Directory via LDAP.
Only users in the AuthorizedUser table can log in.

Features:
- Direct bind authentication (no anonymous LDAP searches)
- Multiple authentication format attempts
- Authorization check via AuthorizedUser model
- Login attempt logging
- Passwords never stored locally
"""

import logging
from ldap3 import Server, Connection, ALL, SIMPLE, Tls, SUBTREE
from ldap3.core.exceptions import (
    LDAPException,
    LDAPBindError,
    LDAPInvalidCredentialsResult,
    LDAPSocketOpenError,
    LDAPNoSuchObjectResult
)
import ssl

from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone

from .models import AuthorizedUser, LoginAttempt

User = get_user_model()
logger = logging.getLogger('ldap_auth')


class LDAPBackend(BaseBackend):
    """
    Custom authentication backend that authenticates against LDAP/AD
    and checks local authorization.
    
    Authentication Flow:
    1. Check if user exists in AuthorizedUser table and is active
    2. Validate username/password via LDAP simple bind
    3. Retrieve user attributes from LDAP (email, name, etc.)
    4. Create or update local Django User with unusable password
    5. Log the login attempt
    6. Return authenticated user or None
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate a user against LDAP and verify local authorization.
        
        Args:
            request: HttpRequest object
            username: CPF number (LDAP sAMAccountName)
            password: User's password (sent to LDAP, never stored)
            
        Returns:
            User object if authentication and authorization succeed
            None if authentication fails or user is not authorized
        """
        if not username or not password:
            logger.warning("Authentication attempt with missing username or password")
            return None
        
        # Normalize username (remove domain if present)
        username = self._normalize_username(username)
        
        # Get client IP and user agent for logging
        ip_address = self._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '') if request else ''
        
        # Step 1: Check local authorization FIRST (before hitting LDAP)
        authorized_user = self._get_authorized_user(username)
        if not authorized_user:
            self._log_attempt(username, 'failed_unauthorized', ip_address, user_agent, 
                            "User not in AuthorizedUser table")
            logger.warning(f"User {username} not authorized in application")
            return None
        
        if not authorized_user.is_active:
            self._log_attempt(username, 'failed_inactive', ip_address, user_agent,
                            "User account is inactive")
            logger.warning(f"User {username} is inactive")
            return None
        
        # Step 1.5: Check if user has a role assigned (required for login)
        if not authorized_user.role or authorized_user.role.strip() == '':
            self._log_attempt(username, 'failed_no_role', ip_address, user_agent,
                            "User has no role assigned")
            logger.warning(f"User {username} has no role assigned - cannot log in")
            return None
        
        # Step 2: Authenticate against LDAP
        ldap_user_data = self._ldap_authenticate(username, password)
        if not ldap_user_data:
            self._log_attempt(username, 'failed_ldap', ip_address, user_agent,
                            "Invalid LDAP credentials")
            logger.info(f"LDAP authentication failed for user: {username}")
            return None
        
        # Step 3: Get or create local Django user
        try:
            user = self._get_or_create_user(username, ldap_user_data, authorized_user)
            
            # Link AuthorizedUser to Django User if not already linked
            if authorized_user.user != user:
                authorized_user.user = user
            
            # Update last login in AuthorizedUser
            authorized_user.last_login = timezone.now()
            if ldap_user_data.get('email'):
                authorized_user.email = ldap_user_data['email']
            authorized_user.save(update_fields=['user', 'last_login', 'email'])
            
            # Log successful login
            self._log_attempt(username, 'success', ip_address, user_agent, None, user)
            
            logger.info(f"User {username} successfully authenticated via LDAP")
            return user
            
        except Exception as e:
            self._log_attempt(username, 'failed_error', ip_address, user_agent, str(e))
            logger.error(f"Error creating/updating user {username}: {str(e)}")
            return None
    
    def _normalize_username(self, username):
        """
        Normalize username by removing domain prefix/suffix.
        
        Examples:
            DOMAIN\\username -> username
            username@domain.com -> username
        """
        # Remove domain prefix (DOMAIN\username)
        if '\\' in username:
            username = username.split('\\')[-1]
        
        # Remove domain suffix (username@domain)
        if '@' in username:
            username = username.split('@')[0]
        
        return username.strip()
    
    def _get_authorized_user(self, username):
        """Get AuthorizedUser instance if exists"""
        try:
            return AuthorizedUser.objects.get(cpf_no=username)
        except AuthorizedUser.DoesNotExist:
            return None
    
    def _ldap_authenticate(self, username, password):
        """
        Authenticate user via LDAP using ONGC-specific method:
        Direct bind with multiple authentication formats.
        
        Args:
            username: CPF Number (e.g., "134084")
            password: User password
            
        Returns:
            dict: User attributes from LDAP if successful
            None: If authentication fails or LDAP server unreachable
        """
        try:
            # Configure TLS settings
            tls_configuration = self._get_tls_config()
            
            # Create LDAP server object
            server = Server(
                settings.LDAP_SERVER,
                use_ssl=settings.LDAP_USE_SSL,
                tls=tls_configuration,
                get_info=ALL,
                connect_timeout=5  # Match working Ethos config
            )
            
            # ONGC AD does not allow anonymous searches, so we authenticate directly
            # Try different authentication formats (order matters - based on working Ethos config)
            auth_formats = [
                f"{username}",  # sAMAccountName (e.g., "134084")
                f"{username}@ONGC.ONGCGroup.co.in",  # userPrincipalName (PRIMARY - WORKS!)
                f"ONGCGROUP\\{username}",  # DOMAIN\username
            ]
            
            logger.debug(f"Attempting LDAP authentication for user: {username}")
            logger.debug(f"LDAP Server: {settings.LDAP_SERVER}")
            logger.debug(f"Base DN: {settings.LDAP_BASE_DN}")
            
            auth_conn = None
            successful_format = None
            connection_error = False
            last_error = None
            
            for auth_user in auth_formats:
                try:
                    logger.debug(f"Trying authentication format: {auth_user}")
                    auth_conn = Connection(
                        server,
                        user=auth_user,
                        password=password,
                        authentication=SIMPLE,
                        auto_bind=True,
                        raise_exceptions=True,
                        receive_timeout=5  # Match working Ethos config
                    )
                    successful_format = auth_user
                    logger.info(f"[OK] LDAP bind successful with format: {successful_format}")
                    break
                except LDAPInvalidCredentialsResult as e:
                    logger.debug(f"[X] Invalid credentials with format: {auth_user}")
                    last_error = f"Invalid credentials: {str(e)}"
                    continue
                except LDAPSocketOpenError as e:
                    logger.warning(f"Cannot connect to LDAP server: {e}")
                    connection_error = True
                    last_error = f"Connection error: {str(e)}"
                    break  # No point trying other formats if server is unreachable
                except Exception as e:
                    logger.debug(f"[X] Authentication error with {auth_user}: {type(e).__name__}: {str(e)}")
                    last_error = f"{type(e).__name__}: {str(e)}"
                    continue
            
            if not auth_conn or not auth_conn.bound:
                if connection_error:
                    logger.warning(f"LDAP server unreachable for user {username} - falling back to Django auth. Last error: {last_error}")
                else:
                    logger.warning(f"LDAP authentication failed for user {username} after trying all formats. Last error: {last_error}")
                return None
            
            # Retrieve user attributes using the authenticated connection
            user_data = {'username': username, 'email': '', 'first_name': '', 'last_name': '', 'full_name': ''}
            
            try:
                base_dn = settings.LDAP_BASE_DN
                if base_dn:
                    logger.debug(f"Retrieving user attributes for {username}")
                    auth_conn.search(
                        search_base=base_dn,
                        search_filter=f'(sAMAccountName={username})',
                        search_scope=SUBTREE,
                        attributes=['cn', 'sAMAccountName', 'mail', 'displayName', 'userPrincipalName']
                    )
                    
                    if auth_conn.entries:
                        entry = auth_conn.entries[0]
                        display_name = str(entry.displayName) if hasattr(entry, 'displayName') and entry.displayName else ''
                        cn = str(entry.cn) if hasattr(entry, 'cn') and entry.cn else ''
                        
                        user_data = {
                            'username': username,
                            'email': str(entry.mail) if hasattr(entry, 'mail') and entry.mail else '',
                            'first_name': display_name.split()[0] if display_name else '',
                            'last_name': ' '.join(display_name.split()[1:]) if display_name and len(display_name.split()) > 1 else '',
                            'full_name': display_name or cn,
                        }
            except Exception as e:
                logger.warning(f"Could not retrieve LDAP attributes: {e}")
                # Continue with basic user data - auth was successful
            
            try:
                auth_conn.unbind()
            except:
                pass
            
            return user_data
            
        except LDAPInvalidCredentialsResult:
            logger.warning(f"Invalid LDAP credentials for user: {username}")
            return None
            
        except LDAPNoSuchObjectResult:
            logger.error(f"LDAP base DN not found: {settings.LDAP_BASE_DN}")
            return None
            
        except (LDAPSocketOpenError, ConnectionError, OSError) as e:
            logger.warning(f"LDAP server unreachable: {str(e)} - falling back to Django authentication")
            return None
            
        except LDAPException as e:
            logger.error(f"LDAP error during authentication: {str(e)}")
            return None
            
        except Exception as e:
            logger.error(f"Unexpected error during LDAP authentication: {str(e)}")
            return None
    
    def _get_tls_config(self):
        """Configure TLS/SSL settings for LDAP connection."""
        if not settings.LDAP_USE_SSL:
            return None
        
        # Determine certificate validation strategy
        if hasattr(settings, 'LDAP_CA_CERT_PATH') and settings.LDAP_CA_CERT_PATH:
            validate = ssl.CERT_REQUIRED
            ca_certs_file = settings.LDAP_CA_CERT_PATH
        elif getattr(settings, 'LDAP_VERIFY_SSL', True):
            validate = ssl.CERT_REQUIRED
            ca_certs_file = None
        else:
            logger.warning("SSL certificate verification is DISABLED - not recommended for production")
            validate = ssl.CERT_NONE
            ca_certs_file = None
        
        tls = Tls(
            validate=validate,
            version=ssl.PROTOCOL_TLSv1_2,
            ca_certs_file=ca_certs_file
        )
        
        return tls
    
    def _get_or_create_user(self, username, ldap_user_data, authorized_user):
        """
        Get or create Django User object.
        
        Security: Password is set to unusable (no local authentication)
        """
        try:
            user = User.objects.get(username=username)
            
            # Update user attributes from LDAP
            user.email = ldap_user_data.get('email', '')
            user.first_name = ldap_user_data.get('first_name', '')
            user.last_name = ldap_user_data.get('last_name', '')
            
            # Set is_staff and is_superuser based on role
            user.is_staff = authorized_user.role == 'admin'
            user.is_superuser = authorized_user.role == 'admin'
            
            # Ensure password is unusable
            if user.has_usable_password():
                user.set_unusable_password()
            
            user.save()
            
        except User.DoesNotExist:
            # Create new user
            user = User.objects.create(
                username=username,
                email=ldap_user_data.get('email', ''),
                first_name=ldap_user_data.get('first_name', ''),
                last_name=ldap_user_data.get('last_name', ''),
                is_staff=authorized_user.role == 'admin',
                is_superuser=authorized_user.role == 'admin'
            )
            
            # Set password to unusable - authentication is LDAP-only
            user.set_unusable_password()
            user.save()
            
            logger.info(f"Created new Django user for LDAP user: {username}")
        
        return user
    
    def _get_client_ip(self, request):
        """Get client IP address from request."""
        if not request:
            return None
        
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _log_attempt(self, username, status, ip_address, user_agent, error_message=None, user=None):
        """Log login attempt to database."""
        try:
            LoginAttempt.objects.create(
                username=username,
                status=status,
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else None,  # Limit length
                error_message=error_message,
                user=user
            )
        except Exception as e:
            logger.error(f"Failed to log login attempt: {str(e)}")
    
    def get_user(self, user_id):
        """Retrieve a user by ID. Required by Django authentication system."""
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
