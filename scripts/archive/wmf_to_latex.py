#!/usr/bin/env python3
"""
wmf_to_latex.py — Extract MathType MTEF from WMF files and convert to LaTeX.

Handles fractions, superscripts, subscripts, radicals, brackets,
n-ary operators (sums, integrals), Greek letters, and basic math symbols.

Usage:
    from wmf_to_latex import extract_latex_from_wmf
    latex = extract_latex_from_wmf('path/to/image1.wmf')
    # Returns: 'f(x)=e^{x}-1' or None if no MathType data
"""

import struct, os

# ── MTEF Tag Constants ──────────────────────────────────────────────────────
TAG_LINE     = 0x01  # Line record
TAG_CHAR     = 0x02  # Character record  
TAG_TMPL     = 0x03  # Template record (fraction, sqrt, etc.)
TAG_PILE     = 0x04  # Pile/matrix
TAG_MATRIX   = 0x05  # Matrix
TAG_EMBELL   = 0x06  # Embellishment (limits, primes, etc.)
TAG_RULER    = 0x07  # Ruler/tab stop
TAG_FONT     = 0x08  # Font record
TAG_SIZE     = 0x09  # Size record
TAG_FULL     = 0x0a  # Full-size font
TAG_SUB      = 0x0b  # Subscript font
TAG_SUB2     = 0x0c  # Second-level subscript
TAG_SYM      = 0x0d  # Symbol font
TAG_STYLE    = 0x10  # Style definition

# Template codes
TMPL_FRAC   = 0x00  # Fraction
TMPL_RAD    = 0x01  # Radical (sqrt)
TMPL_SUP    = 0x02  # Superscript
TMPL_SUB    = 0x03  # Subscript
TMPL_SUBSUP = 0x04  # Subscript + superscript
TMPL_LIM    = 0x05  # Limits (sub above, sup below or vice versa)
TMPL_BRACK  = 0x08  # Bracket/delimiter
TMPL_FENCE  = 0x09  # Fence (parentheses, brackets, etc.)
TMPL_BAR    = 0x0a  # Bar (overline, underline)
TMPL_BOX    = 0x0b  # Box/phantom

# Character mappings: MTEF char code → LaTeX
CHAR_MAP = {
    0x00: '',        # null
    0x01: '+',       # plus placeholder
    0x04: '=',       # equals
    0x08: '(',       # left paren
    0x09: ')',       # right paren
    0x0a: '*',       # asterisk/multiplication
    0x0b: '+',       # plus sign
    0x0c: ',',       # comma
    0x0d: '-',       # minus sign (hyphen)
    0x0e: '.',       # period
    0x0f: '/',       # slash
    0x14: '<',       # less than
    0x15: '=',       # equals (MathType rendition)
    0x16: '>',       # greater than
    0x1e: '[',       # left bracket
    0x1f: ']',       # right bracket
    0x20: '\\infty', # infinity
    0x22: '\\partial', # partial derivative
    0x24: '\\nabla', # nabla
    0x25: '\\in',    # element of
    0x26: '\\notin', # not in
    0x27: '\\ni',    # contains as member
    0x2a: '\\subset', # subset
    0x31: '\\int',   # integral
    0x34: '\\sum',   # summation
    0x35: '\\prod',  # product
    0x3c: '\\sqrt',  # square root
    0x40: '\\forall',# for all
    0x41: '\\exists',# exists
    0x43: '\\neg',   # negation
    0x44: '\\wedge', # logical and
    0x45: '\\vee',   # logical or
    0x50: '\\cup',   # union
    0x51: '\\cap',   # intersection
    0x52: '\\setminus', # set minus
    0x56: '\\circ',  # composition
    0x61: '\\alpha', # alpha
    0x62: '\\beta',  # beta
    0x63: '\\gamma', # gamma
    0x64: '\\delta', # delta
    0x65: '\\varepsilon', # epsilon
    0x67: '\\theta', # theta
    0x6c: '\\lambda', # lambda
    0x6d: '\\mu',    # mu
    0x70: '\\pi',    # pi
    0x72: '\\rho',   # rho
    0x73: '\\sigma', # sigma
    0x76: '\\phi',   # phi
    0x77: '\\omega', # omega
    0xae: '\\neq',   # not equal
    0xb0: '\\equiv', # identical
    0xb1: '\\leq',   # less or equal
    0xb2: '\\geq',   # greater or equal
    0xb3: '\\ll',    # much less
    0xb4: '\\gg',    # much greater
    0xb5: '\\approx', # approximately
    0xc6: '\\leftarrow',  # left arrow
    0xc8: '\\rightarrow', # right arrow
    0xcd: '\\Leftrightarrow', # bi-implication
}

def _find_mtef(data):
    """Find MathType MTEF equation data in WMF binary data.
    Returns (mtef_bytes, start_offset) or (None, -1)."""
    mt_idx = data.find(b'MathType')
    if mt_idx < 0:
        # Try alternative signatures
        for alt in [b'DSMT', b'Eqn']:
            mt_idx = data.find(alt)
            if mt_idx >= 0: break
    if mt_idx < 0:
        return None, -1
    
    # Skip MathType string + null terminator
    pos = mt_idx
    while pos < len(data) and data[pos] != 0:
        pos += 1
    pos += 1  # skip null
    if pos + 28 > len(data):
        return None, -1
    
    # 28-byte MathType header
    header = data[pos:pos+28]
    eq_data = data[pos+28:]
    
    return eq_data, pos+28


def _parse_mtef(bytes_data, depth=0):
    """Recursively parse MTEF equation bytecode into LaTeX string."""
    if not bytes_data or len(bytes_data) == 0:
        return '', 0
    
    result = ''
    pos = 0
    
    while pos < len(bytes_data):
        if pos >= len(bytes_data):
            break
            
        tag = bytes_data[pos]
        
        if tag == TAG_LINE:
            # LINE: tag(1) + line_flags(1) + line_spacing(2) + [child records...]
            if pos + 4 > len(bytes_data): break
            line_flags = bytes_data[pos+1]
            pos += 4
            # Parse children
            child_result = ''
            while pos < len(bytes_data):
                peek = bytes_data[pos] if pos < len(bytes_data) else 0
                if peek == TAG_LINE or peek >= 0x20:
                    break  # Next line or end
                child_text, advance = _parse_mtef(bytes_data[pos:], depth+1)
                if advance == 0:
                    pos += 1
                else:
                    child_result += child_text
                    pos += advance
            result += child_result
            
        elif tag == TAG_CHAR:
            # CHAR: tag(1) + char_code(1)
            if pos + 2 > len(bytes_data): break
            ch = bytes_data[pos+1]
            if 32 <= ch < 127 and ch not in CHAR_MAP:
                result += chr(ch)
            else:
                latex = CHAR_MAP.get(ch, '')
                if not latex:
                    # Try to represent as hex
                    latex = f'[0x{ch:02x}]'
                result += latex
            pos += 2
            
        elif tag == TAG_TMPL:
            # TEMPLATE: tag(1) + tmpl_code(1) + [options...] + [child records...]
            if pos + 2 > len(bytes_data): break
            tmpl_code = bytes_data[pos+1]
            tmpl_data = bytes_data[pos+2:]
            
            if tmpl_code == TMPL_FRAC:
                # Fraction: tmpl_code + num_slot + den_slot
                num_text, num_adv = _parse_mtef(tmpl_data, depth+1)
                den_data = tmpl_data[num_adv:]
                den_text, den_adv = _parse_mtef(den_data, depth+1)
                result += f'\\frac{{{num_text}}}{{{den_text}}}'
                pos += 2 + num_adv + den_adv
                
            elif tmpl_code == TMPL_RAD:
                # Radical: tmpl_code + [deg_slot?] + radicand_slot
                rad_text, rad_adv = _parse_mtef(tmpl_data, depth+1)
                result += f'\\sqrt{{{rad_text}}}'
                pos += 2 + rad_adv
                
            elif tmpl_code == TMPL_SUP:
                # Superscript: base_slot + sup_slot
                base_text, base_adv = _parse_mtef(tmpl_data, depth+1)
                sup_data = tmpl_data[base_adv:]
                sup_text, sup_adv = _parse_mtef(sup_data, depth+1)
                if len(base_text) > 1:
                    result += f'{{{base_text}}}^{{{sup_text}}}'
                else:
                    result += f'{base_text}^{{{sup_text}}}'
                pos += 2 + base_adv + sup_adv
                
            elif tmpl_code == TMPL_SUB:
                # Subscript: base_slot + sub_slot
                base_text, base_adv = _parse_mtef(tmpl_data, depth+1)
                sub_data = tmpl_data[base_adv:]
                sub_text, sub_adv = _parse_mtef(sub_data, depth+1)
                result += f'{base_text}_{{{sub_text}}}'
                pos += 2 + base_adv + sub_adv
                
            elif tmpl_code == TMPL_SUBSUP:
                # Subscript+Superscript: base + sub + sup
                base_text, base_adv = _parse_mtef(tmpl_data, depth+1)
                rest1 = tmpl_data[base_adv:]
                sub_text, sub_adv = _parse_mtef(rest1, depth+1)
                rest2 = rest1[sub_adv:]
                sup_text, sup_adv = _parse_mtef(rest2, depth+1)
                result += f'{base_text}_{{{sub_text}}}^{{{sup_text}}}'
                pos += 2 + base_adv + sub_adv + sup_adv
                
            elif tmpl_code == TMPL_BRACK or tmpl_code == TMPL_FENCE:
                # Brackets: opening_delim + content + closing_delim
                bracket_text, bracket_adv = _parse_mtef(tmpl_data, depth+1)
                result += f'\\left( {bracket_text} \\right)'
                pos += 2 + bracket_adv
                
            else:
                # Unknown template — just parse children
                child_text, child_adv = _parse_mtef(tmpl_data, depth+1)
                if child_text:
                    result += child_text
                pos += 2 + child_adv
                
        elif tag == TAG_FONT:
            # FONT: tag(1) + font_number(1) + style(1)
            if pos + 3 > len(bytes_data): break
            pos += 3  # Skip font info
            
        elif tag in (TAG_SIZE, TAG_STYLE, TAG_SYM):
            # SIZE/STYLE: tag(1) + value(1)
            pos += 2
            
        elif tag == TAG_EMBELL:
            # Embellishment: tag(1) + emb_type(1) + children
            if pos + 2 > len(bytes_data): break
            emb_data = bytes_data[pos+2:]
            emb_text, emb_adv = _parse_mtef(emb_data, depth+1)
            result += emb_text
            pos += 2 + emb_adv
            
        elif tag == TAG_RULER or tag >= 0x20:
            # Ruler or unknown — stop parsing this level
            break
            
        else:
            # Unknown tag — skip
            pos += 1
            
    return result, pos


def extract_latex_from_wmf(wmf_path):
    """Extract LaTeX equation string from a WMF file containing MathType data.
    Returns LaTeX string or None if no MathType data found."""
    if not os.path.exists(wmf_path):
        return None
    
    with open(wmf_path, 'rb') as f:
        data = f.read()
    
    # Check for Placeable WMF header
    if data[:4] == b'\xd7\xcd\xc6\x9a':
        # Skip 22-byte Placeable header
        pass
    
    eq_data, offset = _find_mtef(data)
    if not eq_data or len(eq_data) < 4:
        return None
    
    try:
        latex, consumed = _parse_mtef(eq_data)
        # Clean up: remove debugging artifacts
        import re
        latex = re.sub(r'\[0x[0-9a-f]+\]', '', latex)
        latex = latex.strip()
        return latex if latex else None
    except Exception:
        return None


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        path = sys.argv[1]
        latex = extract_latex_from_wmf(path)
        if latex:
            print(f"LaTeX: {latex}")
        else:
            print("No MathType data found")