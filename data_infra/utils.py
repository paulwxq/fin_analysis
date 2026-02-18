def transform_code(raw_code: str) -> str:
    """
    Standardize stock code from 'prefix + code' to 'code.SUFFIX'.
    
    Examples:
        sh600000 -> 600000.SH
        sz000001 -> 000001.SZ
        bj430090 -> 430090.BJ
    
    Args:
        raw_code: The raw stock code string from CSV (e.g., 'sh600000').
        
    Returns:
        Standardized code string.
        
    Raises:
        ValueError: If the code format is unrecognized.
    """
    raw_code = raw_code.lower().strip()
    
    if raw_code.startswith("sh"):
        return f"{raw_code[2:]}.SH"
    elif raw_code.startswith("sz"):
        return f"{raw_code[2:]}.SZ"
    elif raw_code.startswith("bj"):
        return f"{raw_code[2:]}.BJ"
    
    # Fallback/Error handling
    # If pure number (rare in this dataset but possible), we might need logic.
    # For now, assuming dataset strictly follows prefix rule.
    raise ValueError(f"Unknown stock code format: {raw_code}")
