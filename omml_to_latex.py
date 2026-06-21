#!/usr/bin/env python3
"""
omml_to_latex.py — Convert Office Math Markup Language (OMML) to LaTeX

Handles the math elements found in Greek Panhellenic math exam DOCX files:
fractions, superscripts, subscripts, radicals, brackets, operators,
limits, integrals, sums, and Greek letters.

Usage:
    from omml_to_latex import omml_to_latex, process_paragraph
    latex = omml_to_latex(oMath_xml_string)
"""

import re

# ── OMML tags to LaTeX symbols ──────────────────────────────────────────────

OMML_SYMBOLS = {
    # Greek letters
    'α': '\\alpha', 'β': '\\beta', 'γ': '\\gamma', 'δ': '\\delta',
    'ε': '\\varepsilon', 'ζ': '\\zeta', 'η': '\\eta', 'θ': '\\theta',
    'ι': '\\iota', 'κ': '\\kappa', 'λ': '\\lambda', 'μ': '\\mu',
    'ν': '\\nu', 'ξ': '\\xi', 'ο': 'o', 'π': '\\pi', 'ρ': '\\rho',
    'σ': '\\sigma', 'τ': '\\tau', 'υ': '\\upsilon', 'φ': '\\phi',
    'χ': '\\chi', 'ψ': '\\psi', 'ω': '\\omega',
    'Α': 'A', 'Β': 'B', 'Γ': '\\Gamma', 'Δ': '\\Delta',
    'Ε': 'E', 'Ζ': 'Z', 'Η': 'H', 'Θ': '\\Theta',
    'Ι': 'I', 'Κ': 'K', 'Λ': '\\Lambda', 'Μ': 'M',
    'Ν': 'N', 'Ξ': '\\Xi', 'Ο': 'O', 'Π': '\\Pi',
    'Ρ': 'P', 'Σ': '\\Sigma', 'Τ': 'T', 'Υ': '\\Upsilon',
    'Φ': '\\Phi', 'Χ': 'X', 'Ψ': '\\Psi', 'Ω': '\\Omega',
    
    # Math operators
    '∫': '\\int', '∬': '\\iint', '∮': '\\oint',
    '∑': '\\sum', '∏': '\\prod',
    '√': '\\sqrt', '∛': '\\sqrt[3]', '∜': '\\sqrt[4]',
    '∞': '\\infty', '∂': '\\partial',
    '∇': '\\nabla', '∅': '\\emptyset',
    '∈': '\\in', '∉': '\\notin', '⊂': '\\subset', '⊆': '\\subseteq',
    '∪': '\\cup', '∩': '\\cap',
    '≤': '\\leq', '≥': '\\geq', '≠': '\\neq',
    '→': '\\rightarrow', '←': '\\leftarrow', '⇒': '\\Rightarrow',
    '≈': '\\approx', '≅': '\\cong', '≡': '\\equiv',
    '∀': '\\forall', '∃': '\\exists',
}

def _extract_text(xml_str):
    """Extract all <m:t> text content from an OMML element."""
    return ''.join(re.findall(r'<m:t[^>]*>([^<]*)</m:t>', xml_str))

def omml_to_latex(xml_str):
    """Convert an OMML math element to LaTeX string."""
    if not xml_str or '<m:' not in xml_str:
        return xml_str
    
    result = xml_str
    
    # Replace OMML constructs with LaTeX
    # Fractions: <m:f><m:num>...</m:num><m:den>...</m:den></m:f>
    def replace_fraction(m):
        num = omml_to_latex(m.group(1))
        den = omml_to_latex(m.group(2))
        return f'\\frac{{{num}}}{{{den}}}'
    result = re.sub(
        r'<m:f[^>]*>.*?<m:num>(.*?)</m:num>.*?<m:den>(.*?)</m:den>.*?</m:f>',
        replace_fraction, result, flags=re.DOTALL
    )
    
    # Superscripts: <m:sSup><m:e>...</m:e><m:sup>...</m:sup></m:sSup>
    def replace_sup(m):
        base = omml_to_latex(m.group(1))
        sup = omml_to_latex(m.group(2))
        return f'{base}^{{{sup}}}'
    result = re.sub(
        r'<m:sSup[^>]*>.*?<m:e>(.*?)</m:e>.*?<m:sup>(.*?)</m:sup>.*?</m:sSup>',
        replace_sup, result, flags=re.DOTALL
    )
    
    # Subscripts: <m:sSub><m:e>...</m:e><m:sub>...</m:sub></m:sSub>
    def replace_sub(m):
        base = omml_to_latex(m.group(1))
        sub = omml_to_latex(m.group(2))
        return f'{base}_{{{sub}}}'
    result = re.sub(
        r'<m:sSub[^>]*>.*?<m:e>(.*?)</m:e>.*?<m:sub>(.*?)</m:sub>.*?</m:sSub>',
        replace_sub, result, flags=re.DOTALL
    )
    
    # Sub+Sup: <m:sSubSup><m:e>...</m:e><m:sub>...</m:sub><m:sup>...</m:sup>
    def replace_subsup(m):
        base = omml_to_latex(m.group(1))
        sub = omml_to_latex(m.group(2))
        sup = omml_to_latex(m.group(3))
        return f'{base}_{{{sub}}}^{{{sup}}}'
    result = re.sub(
        r'<m:sSubSup[^>]*>.*?<m:e>(.*?)</m:e>.*?<m:sub>(.*?)</m:sub>.*?<m:sup>(.*?)</m:sup>.*?</m:sSubSup>',
        replace_subsup, result, flags=re.DOTALL
    )
    
    # Radicals (square roots): <m:rad><m:deg>...</m:deg><m:e>...</m:e></m:rad>
    def replace_rad(m):
        deg_xml = m.group(1)
        e_xml = m.group(2)
        content = omml_to_latex(e_xml)
        if 'm:deg' in deg_xml and deg_xml.strip():
            deg = _extract_text(deg_xml).strip()
            if deg:
                return f'\\sqrt[{deg}]{{{content}}}'
        return f'\\sqrt{{{content}}}'
    result = re.sub(
        r'<m:rad[^>]*>(.*?<m:deg[^>]*>.*?</m:deg>)?.*?<m:e>(.*?)</m:e>.*?</m:rad>',
        replace_rad, result, flags=re.DOTALL
    )
    
    # Grouped characters / brackets
    def replace_groupChr(m):
        chr_xml = m.group(1)
        content = omml_to_latex(m.group(2))
        chr_text = _extract_text(chr_xml).strip()
        if chr_text in ('[',']'):
            return f'\\left[{content}\\right]'
        elif chr_text in ('{','}'):
            return f'\\{{{content}\\}}'
        elif chr_text in ('|','‖'):
            return f'\\left|{content}\\right|'
        return f'\\left({content}\\right)'
    result = re.sub(
        r'<m:d[^>]*>.*?<m:dPr>.*?<m:begChr>(.*?)</m:begChr>.*?<m:endChr>(.*?)</m:endChr>.*?</m:dPr>.*?<m:e>(.*?)</m:e>.*?</m:d>',
        replace_groupChr, result, flags=re.DOTALL
    )
    
    # N-ary operators (sum, product, integral with limits)
    def replace_nary(m):
        op_xml = m.group(1)
        sub_xml = m.group(2) if 'm:sub' in m.group(0) else ''
        sup_xml = m.group(3) if 'm:sup' in m.group(0) else ''
        e_xml = m.group(4)
        
        op_text = _extract_text(op_xml).strip()
        op = OMML_SYMBOLS.get(op_text, op_text)
        
        sub = omml_to_latex(sub_xml) if sub_xml else ''
        sup = omml_to_latex(sup_xml) if sup_xml else ''
        content = omml_to_latex(e_xml) if e_xml else ''
        
        limits = ''
        if sub:
            limits += f'_{{{sub}}}'
        if sup:
            limits += f'^{{{sup}}}'
        
        return f'{op}{limits}{{{content}}}'
    result = re.sub(
        r'<m:nary[^>]*>.*?<m:naryPr>.*?<m:chr>(.*?)</m:chr>.*?</m:naryPr>(?:.*?<m:sub>(.*?)</m:sub>)?(?:.*?<m:sup>(.*?)</m:sup>)?.*?<m:e>(.*?)</m:e>.*?</m:nary>',
        replace_nary, result, flags=re.DOTALL
    )
    
    # Function apply: <m:func><m:fName>...</m:fName><m:e>...</m:e></m:func>
    def replace_func(m):
        name = omml_to_latex(m.group(1))
        arg = omml_to_latex(m.group(2))
        # Common function names
        funcs = {'lim': '\\lim', 'log': '\\log', 'ln': '\\ln', 
                 'sin': '\\sin', 'cos': '\\cos', 'tan': '\\tan',
                 'ημ': '\\sin', 'συν': '\\cos', 'εφ': '\\tan',
                 'ημίτονο': '\\sin', 'συνημίτονο': '\\cos'}
        name_stripped = _extract_text(name).strip()
        latex_name = funcs.get(name_stripped, name_stripped)
        return f'{latex_name}{{{arg}}}'
    result = re.sub(
        r'<m:func[^>]*>.*?<m:fName>(.*?)</m:fName>.*?<m:e>(.*?)</m:e>.*?</m:func>',
        replace_func, result, flags=re.DOTALL
    )
    
    # Accents (bar, hat, dot, etc.)
    def replace_acc(m):
        acc_xml = m.group(1)
        content = omml_to_latex(m.group(2))
        acc_text = _extract_text(acc_xml).strip()
        accents = {'̅': '\\overline', '́': '\\acute', '̂': '\\hat',
                   '̇': '\\dot', '̈': '\\ddot', '⃗': '\\vec',
                   'bar': '\\bar', 'hat': '\\hat'}
        acc = accents.get(acc_text, '\\overline')
        return f'{acc}{{{content}}}'
    result = re.sub(
        r'<m:acc[^>]*>.*?<m:accPr>.*?<m:chr>(.*?)</m:chr>.*?</m:accPr>.*?<m:e>(.*?)</m:e>.*?</m:acc>',
        replace_acc, result, flags=re.DOTALL
    )
    
    # Matrix
    def replace_m(m):
        rows_xml = m.group(1)
        rows = re.findall(r'<m:mr>(.*?)</m:mr>', rows_xml, re.DOTALL)
        latex_rows = []
        for row in rows:
            cells = re.findall(r'<m:e>(.*?)</m:e>', row, re.DOTALL)
            latex_cells = [omml_to_latex(c) for c in cells]
            latex_rows.append(' & '.join(latex_cells))
        return '\\begin{bmatrix} ' + ' \\\\ '.join(latex_rows) + ' \\end{bmatrix}'
    result = re.sub(
        r'<m:m[^>]*>(.*?)</m:m>',
        replace_m, result, flags=re.DOTALL
    )
    
    # Remove any remaining XML tags inside math
    result = re.sub(r'<[^>]+>', '', result)
    
    # Clean up whitespace
    result = result.strip()
    
    # Convert Greek text to math symbols
    for gk, latex in OMML_SYMBOLS.items():
        if len(gk) == 1 and gk.isalpha():
            # Only replace single Greek letters that are alone or in math context
            pass  # Let KaTeX handle unicode
    
    return result

def process_paragraph(paragraph):
    """Process a paragraph, converting OMML math to LaTeX delimiters.
    Returns (text, has_math) tuple."""
    xml = paragraph._element.xml
    
    if '<m:oMath' not in xml and '<m:oMathPara' not in xml:
        return paragraph.text.strip(), False
    
    text = paragraph.text.strip()
    if not text:
        return paragraph.text.strip(), False
    
    # Replace each oMath block with $...$ LaTeX
    result = xml
    for match in re.finditer(r'<m:oMath[^>]*>(.*?)</m:oMath>', xml, re.DOTALL):
        omath_xml = match.group(0)
        inner = match.group(1)
        latex = omml_to_latex(inner)
        if latex:
            escaped_latex = latex.replace('\\', '\\\\')
            result = result.replace(omath_xml, f'${escaped_latex}$')
    
    # Extract text from the modified XML
    # Strip XML tags to get plain text with $...$ LaTeX inline
    result_text = re.sub(r'<[^>]+>', '', result)
    # Clean multiple spaces
    result_text = re.sub(r' +', ' ', result_text).strip()
    
    return result_text, True

def extract_paragraph_text(paragraph):
    """Extract text from a paragraph, preserving inline math as $...$ LaTeX."""
    return process_paragraph(paragraph)[0]