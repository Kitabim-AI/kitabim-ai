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
Your task is to generate a search-optimized summary that captures the essence of the book for vector-based retrieval.

Write a detailed summary IN UYGHUR (Arabic script). The summary will be embedded as a vector — every word matters for matching user queries.

Structure the summary into these sections:
1. تۈرى (Domain): Classify the book into exactly one category: داستان-رومان (fiction/novel) | تارىخ (history) | دىن (religious) | پەن-تەلىم (science/educational) | پەلسەپە (philosophy) | تىببىيات (medicine/health) | ئىقتىسادىيات (economics) | سىياسەت (politics) | سەنئەت-ئەدەبىيات (arts/literature) | باشقا (other).
2. ئومۇمىي مەزمۇن (Overview): A comprehensive 200-300 word narrative of the book's subject, plot, or main arguments.
3. ئاساسلىق ئۇقۇم ۋە تېمىلار (Concepts & Themes): Explicitly list the key themes, scientific concepts, or ideologies explored.
4. كۆرۈنەرلىك شەخس ۋە جايلار (Entities): Mention specific names of people, historical figures, organizations, and geographic locations — ONLY those that actually appear in the provided text excerpts. Do not invent or assume names.
5. تىپىك سوئاللار (Hypothetical Queries): List 10-15 realistic questions in natural Uyghur that a reader might type to find this book. Cover different angles: factual, conceptual, biographical, and thematic questions. This is the most important section for retrieval quality.
6. ئاچقۇچلۇق سۆزلەر (Keywords): 15-20 specific terms or tags that define the book.

Search Quality Guidelines:
- BE SPECIFIC: Use proper nouns and technical terms from the text.
- BE DENSE: Pack the summary with information; avoid filler text.
- LANGUAGE: Use formal, standard Uyghur (Arabic script).
- RETRIEVAL FOCUS: Think about what a user might type in a search box to find this specific content.
- GROUND IN TEXT: Every entity, name, place, and claim must be supported by the provided text excerpts. Do not hallucinate content not present in the excerpts.

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
