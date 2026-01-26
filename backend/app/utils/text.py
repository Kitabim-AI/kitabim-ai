import re

def clean_uyghur_text(text: str) -> str:
    if not text:
        return ""
    
    # 1. Join words split by hyphen/dash at the end of a line
    text = re.sub(r'(\w)[-—–_]\s*\n\s*(\w)', r'\1\2', text)
    
    # 2. Standardize hyphens/dashes at line ends
    text = re.sub(r'(\w)[-—–_]\s*\n\s*', r'\1', text)
    
    # 3. Clean up tatweels if they are at the end of a line (filler and joiner)
    text = re.sub(r'ـ+\s*\n\s*', '', text)
    
    # 4. Split by paragraphs (double newlines or more)
    paragraphs = re.split(r'\n\s*\n', text)
    cleaned_paragraphs = []
    
    for p in paragraphs:
        if not p.strip(): continue
        
        # Split into individual lines and clean them
        lines = [l.strip() for l in p.split('\n') if l.strip()]
        if not lines: continue
        
        result_para = ""
        for i in range(len(lines)):
            line = lines[i]
            if i < len(lines) - 1:
                next_line = lines[i+1]
                
                # Uyghur enders: . ؟ ! : ؛ or quotes/brackets » " ” ) ] } ﴾ ﴿ …
                is_ending = re.search(r'[.؟!:؛»"”)\]}﴾﴿…]\s*$', line)
                is_new_item = re.match(r'^\s*([-—–*•\d])', next_line)
                
                if is_ending or is_new_item:
                    result_para += line + "\n"
                else:
                    # join with a space to flow the sentence continuously
                    result_para += line + " "
            else:
                # Last line of the block
                result_para += line
        
        cleaned_paragraphs.append(result_para.strip())
        
    return "\n\n".join(cleaned_paragraphs)
