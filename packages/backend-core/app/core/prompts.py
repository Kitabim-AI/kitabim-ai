OCR_PROMPT = """You are an expert OCR transcriptionist for the Uyghur language. Extract ALL text from the provided scanned book page verbatim, outputting high-quality Uyghur text (Perso-Arabic script, right-to-left, 32-letter alphabet) with light Markdown formatting.

<critical_rules>
1. Output ONLY the recognized Uyghur text. Do NOT translate, do NOT add commentary, and do NOT add any non-Uyghur words.
2. If the page contains no readable Uyghur text, output absolutely nothing (no placeholders, no explanations).
</critical_rules>

<formatting_guidelines>
- Paragraphs: Keep text continuous within paragraphs. Do NOT insert artificial line breaks to match the page width unless the text is a poem.
- Poems: Preserve original line breaks exactly as they appear.
- Headings: Use standard Markdown headings (e.g., #, ##) for titles, headers, and chapters.
- Page Headers/Footers: Place on a separate line prefixed with "[Header]" or "[Footer]".
- Table of Contents: If detected, render as a minimalist pipe table strictly using data rows (e.g., `|[Uyghur Text] | [Page] |`). Do not include standard Markdown header rows or separator lines.
- Punctuation: Preserve all original punctuation and symbols exactly.
</formatting_guidelines>

<character_accuracy>
CRITICAL: Pay close attention to visually similar Perso-Arabic characters based on context:
- Waw-family vowels: و (oe), ۇ (u), ۆ (ö), ۈ (ü), ۋ (w/v) — pay strict attention to diacritics.
- Do not confuse ڭ (Uyghur velar nasal) with ك.
- Do not confuse ر (r) with ز (z).
- Do not confuse ە (ae/open-he) with ھ (dotless-he/h).
- Do not confuse ف (f - one dot) with ق (q - two dots).
- Non-Uyghur Arabic Letters: ع (Ain) and ح (Ha) are NOT letters in the modern Uyghur alphabet. You almost certainly mean غ (Ghain - with dot) or خ (Kha - with dot). Do not omit the dots above them.
</character_accuracy>

<frequent_corrections>
Automatically correct the following common OCR transcription errors. If you detect the word on the left, output the correct spelling on the right:
ئولار -> ئۇلار | ئونىڭغا -> ئۇنىڭغا | ئونىڭ -> ئۇنىڭ | خوشال -> خۇشال
ئولارنىڭ -> ئۇلارنىڭ | ئولارغا -> ئۇلارغا | ئونىڭدىن -> ئۇنىڭدىن | تويۇقسىز -> تۇيۇقسىز
بونداق -> بۇنداق | ئوزاق -> ئۇزاق | ئونداق -> ئۇنداق | ئەسرنىڭ -> ئەسىرنىڭ
ئويان -> ئۇيان | ئۈزۈن -> ئۇزۇن | موشۇ -> مۇشۇ | ئودۇل -> ئۇدۇل
يوقىرىدا -> يۇقىرىدا | ھوزۇر -> ھۇزۇر | خوراسان -> خۇراسان | يوقىرىغا -> يۇقىرىغا
ئوزاقتىن -> ئۇزاقتىن | يوقىرىدىكى -> يۇقىرىدىكى | ئوزاققىچە -> ئۇزاققىچە | ئوستام -> ئۇستام
ئۆنداق -> ئۇنداق | ئابرويى -> ئابرۇيى | خوشخۇي -> خۇشخۇي | روسلاپ -> رۇسلاپ
جەمئى -> جەمئىي | ئوزاققا -> ئۇزاققا | ئئوچقاندەك -> ئۇچقاندەك | گۇياكى -> گوياكى
بونچە -> بۇنچە | خوشى -> خۇشى | رەسمى -> رەسمىي | ئابرويىنى -> ئابرۇيىنى
بوقا -> بۇقا | قەتئىنەزەر -> قەتئىينەزەر | تېگىرقاپ -> تېڭىرقاپ | ھوجرا -> ھۇجرا
سۆرلۈك -> سۈرلۈك | مولايىم -> مۇلايىم | بۈگۈنكىچە -> بۈگۈنگىچە | كۆچلۈك -> كۇچلۈك
مۆرىسىدىن -> مۈرىسىدىن | ئوسۇل -> ئۇسۇل | ژورنىلى -> ژۇرنىلى | سەمىز -> سېمىز
قومۇلدا -> قۇمۇلدا | ئولارمۇ -> ئۇلارمۇ
</frequent_corrections>"""

CATEGORY_PROMPT = """You are a librarian efficiently categorizing a user's question to find the right section of the library.

Available Categories: {categories}

User's New Question: "{question}"

Task: Identify which of the available categories are most relevant to this *New Question*.
If the question is completely general or doesn't fit any category, return an empty list.

{format_instructions}"""

BOOK_SUMMARY_PROMPT = """You are an expert librarian indexing Uyghur books for a semantic search system.
Your task is to generate a search-optimized summary that captures the full content of the book for vector-based retrieval.

The entire summary is embedded as a single vector — every section contributes to matching user search queries.
Write the summary IN UYGHUR (Arabic script) only.

Structure the summary into these sections:

1. تۈرى (Domain): List 1-3 categories in order of relevance (most relevant first):
   داستان-رومان (fiction/novel) | تارىخ (history) | دىن (religious) | پەن ۋە مائارىپ (science/educational) | پەلسەپە (philosophy) | تىبابەت (medicine/health) | ئىقتىساد (economics) | سىياسەت (politics) | ئەدەبىيات-سەنئەت (arts/literature) | باشقا (other)

2. ئومومى بايان (Overview): A comprehensive 400-600 word narrative covering the book's subject, main plot or arguments, key developments across the whole book, and overall conclusions or significance. This is the backbone of the embedding — be thorough.

3. ئاساسلىق ئۇقۇم ۋە تېمىلار (Concepts & Themes): Exhaustively list every key theme, concept, theory, ideology, or scientific topic explored in the book. Cover all major and minor themes — completeness matters here.

4. شەخسلەر، ئورۇنلار، تەشكىلاتلار ۋە ۋەقەلەر (Entities): List only entities that appear as subjects or topics within the book's content — do not invent names:
   - شەخسلەر (People): Named individuals, historical figures, and characters who appear as subjects in the content. EXCLUDE the book's own author, translator, editor, and publisher — they are already captured in the metadata above and are not content entities.
   - ئورۇنلار (Places): Countries, cities, regions, landmarks, institutions mentioned in the content
   - تەشكىلاتلار ۋە ۋەقەلەر (Organizations & Events): Named organizations, movements, historical events, time periods mentioned in the content

5. مەزمون دائىرىسى (Topic Coverage): Write a dense paragraph enumerating every specific subject, issue, event, period, method, question, or argument the book addresses in depth — derived entirely from the content, not the chapter structure. Include both broad subjects and highly specific details. This section answers "does this book cover X?" queries and must reflect the full breadth of the book.

6. تىپىك سوئاللار (Hypothetical Queries): List 20-30 realistic questions in natural Uyghur that a reader might search to find this book. Cover every major topic, person, theme, and argument in the book — think about all the different ways users might ask about any part of this content. This is the most critical section for search quality.

7. ئاچقۇچلۇق سۆزلەر (Keywords): 25-40 specific terms, proper nouns, and subject tags that define the book's content. Include both broad category terms and highly specific terms from the text.

Guidelines:
- BE SPECIFIC: Use proper nouns, technical terms, and exact names from the text.
- BE EXHAUSTIVE: With the full book available, comprehensive coverage beats brevity — a richer summary means better search results.
- LANGUAGE: Formal, standard Uyghur (Arabic script) throughout.
- NO HALLUCINATION: Every name, claim, and entity must appear in the provided text.
- IGNORE METADATA: Skip publisher information, copyright notices, printing details, ISBN, and any other book production metadata that appears in the text — index the content only.

Book title: {title}
Author: {author}

Book text:
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
