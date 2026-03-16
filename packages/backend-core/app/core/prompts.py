OCR_PROMPT = """This is a scanned page from a published Uyghur book. Your task is to extract ALL text from this image verbatim as high-quality Uyghur text with light Markdown structure. The text is written in Uyghur using the Perso-Arabic script (right-to-left, 32-letter Uyghur alphabet). 

CRITICAL: Output ONLY the Uyghur text as it appears on the page. Do NOT translate into any other language. Do NOT add any non-Uyghur words. Do NOT add commentary, explanations, or any text that is not on the page. 

Rules: 
1. If it is NOT a poem, DO NOT break sentences into multiple lines to match page width; provide continuous text for each paragraph. 
2. Maintain separate paragraphs. 
3. Preserve punctuation exactly and keep Uyghur symbols & Arabic script. 
4. Identify and preserve structure: use Markdown headings for titles/headers/chapters, if a table of contents is detected render it as a Markdown pipe table (data rows only, no header row and no separator line, one row per entry, Uyghur text on the left, numbers on the right), keep poems with their original line breaks, and include header/footer text (if present) on separate lines, prefixed with "[Header]" or "[Footer]". 
5. If the page contains no readable Uyghur text, output nothing at all — no placeholders, no explanations, no filler text. 
6. Output ONLY the recognized Uyghur text with the minimal Markdown needed for structure. 
7. CRITICAL — Uyghur Arabic-script character accuracy. These character pairs are visually similar but distinct; choose carefully based on context: 
    - Waw-family vowels: و (oe) vs ۇ (u) vs ۆ (ö) vs ۈ (ü) vs ۋ (ve) — ۈ , ۇ , ۋ and ۆ carry diacritics above; 
    - Kaf/Gaf/Ng: ك (k) vs گ (g) vs ڭ (ng) — ڭ is the Uyghur velar nasal, distinct from both ك and گ. 
    - Nun vs Kaf/Ng: ن (n) must not be read as ك or ڭ. 
    - Reh vs Zain: ر (r) vs ز (z) — these look similar; use word context to decide. 
    - He variants: ە (ae/open-he) vs ھ (dotless-he/h) — both are common in Uyghur, context-dependent. 
    - Ain vs Ghain: ع vs غ — غ has a dot above; do not omit it. ع is not an Uyghur chapter.
    - He vs Ha: ح vs خ — خ has a dot above; do not omit it. ح is not an Uyghur chapter.
    - Fa vs Qaf: ف (f) vs ق (q) — ق has two dots above; do not confuse with ف which has one dot above."""

CATEGORY_PROMPT = """You are a librarian efficiently categorizing a user's question to find the right section of the library.

Available Categories: {categories}

User's New Question: "{question}"

Task: Identify which of the available categories are most relevant to this *New Question*.
If the question is completely general or doesn't fit any category, return an empty list.

{format_instructions}"""

BOOK_SUMMARY_PROMPT = """You are an expert librarian indexing Uyghur books for a semantic search system.
Your task is to generate a search-optimized summary that captures the essence of the book for vector-based retrieval.

Write a detailed summary IN UYGHUR (Arabic script). The summary will be embedded as a vector — every word matters for matching user queries.

Structure the summary into these sections:
1. ئومۇمىي مەزمۇن (Overview): A comprehensive 200-300 word narrative of the book's subject, plot, or main arguments.
2. ئاساسلىق ئۇقۇم ۋە تېمىلار (Concepts & Themes): Explicitly list the key themes, scientific concepts, or ideologies explored.
3. كۆرۈنەرلىك شەخس ۋە جايلار (Entities): Mention specific names of people, historical figures, organizations, and geographic locations.
4. تىپىك سوئاللار (Hypothetical Queries): List 5-7 questions that this book is best suited to answer. This helps align the document vector with potential user questions.
5. ئاچقۇچلۇق سۆزلەر (Keywords): 15-20 specific terms or tags that define the book.

Search Quality Guidelines:
- BE SPECIFIC: Use proper nouns and technical terms from the text.
- BE DENSE: Pack the summary with information; avoid filler text.
- LANGUAGE: Use formal, standard Uyghur (Arabic script).
- RETRIEVAL FOCUS: Think about what a user might type in a search box to find this specific content.

Book title: {title}
Author: {author}

Book text (excerpts):
{text}

Summary:"""

RAG_PROMPT_TEMPLATE = """
[CONTEXT START]
{context}
[CONTEXT END]

{instructions}

[CHAT HISTORY START]
{chat_history}
[CHAT HISTORY END]

Question: {question}
"""
