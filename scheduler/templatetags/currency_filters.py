from django import template
import locale

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary"""
    if dictionary is None:
        return None
    return dictionary.get(key, '')

@register.filter
def indian_currency(value):
    """Format currency in Indian numbering system with comma separation"""
    try:
        # Convert to float if it's a string
        if isinstance(value, str):
            value = float(value)
        
        # Handle None or zero values
        if not value:
            return "0"
            
        # Convert to integer for currency display
        value = int(value)
        
        # Format with Indian comma system
        # First convert to string
        value_str = str(value)
        
        # If less than 1000, return as is
        if len(value_str) <= 3:
            return value_str
        
        # For Indian system: last 3 digits, then groups of 2
        last_three = value_str[-3:]
        remaining = value_str[:-3]
        
        # Add commas every 2 digits for the remaining part (from right to left)
        formatted_remaining = ""
        for i, digit in enumerate(reversed(remaining)):
            if i > 0 and i % 2 == 0:
                formatted_remaining = "," + formatted_remaining
            formatted_remaining = digit + formatted_remaining
        
        return formatted_remaining + "," + last_three
        
    except (ValueError, TypeError):
        return str(value) if value is not None else "0"

@register.filter
def format_solve_time(value):
    """Format solve time properly"""
    try:
        if not value or value == 0:
            return "< 1s"
        
        # Convert to float
        time_value = float(value)
        
        if time_value < 1:
            return "< 1s"
        elif time_value < 60:
            return f"{time_value:.1f}s"
        else:
            minutes = int(time_value // 60)
            seconds = time_value % 60
            return f"{minutes}m {seconds:.0f}s"
            
    except (ValueError, TypeError):
        return "< 1s"

@register.filter
def indian_currency_short(value):
    """Format currency in short Indian form (L for Lakhs, Cr for Crores)"""
    try:
        # Convert to float if it's a string
        if isinstance(value, str):
            value = float(value)
        
        # Handle None or zero values
        if not value:
            return "0"
            
        # Convert to integer for currency display
        value = int(value)
        
        # Convert to short form
        if value >= 10000000:  # 1 crore or more
            crores = value / 10000000
            if crores >= 100:
                return f"{crores:.0f} Cr"
            else:
                return f"{crores:.1f} Cr"
        elif value >= 100000:  # 1 lakh or more
            lakhs = value / 100000
            if lakhs >= 100:
                return f"{lakhs:.0f} L"
            else:
                return f"{lakhs:.1f} L"
        elif value >= 1000:  # 1 thousand or more
            thousands = value / 1000
            return f"{thousands:.1f} K"
        else:
            return str(value)
        
    except (ValueError, TypeError):
        return str(value) if value is not None else "0"

@register.filter
def lookup(dictionary, key):
    """Lookup a key in a dictionary"""
    if hasattr(dictionary, 'get'):
        return dictionary.get(key)
    return None