-- Dumped from database version 18.3 (Postgres.app)
-- Dumped by pg_dump version 18.3

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET search_path = public;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: delete_expired_tokens(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.delete_expired_tokens() RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    DELETE FROM refresh_tokens WHERE expires_at < NOW();
END;
$$;


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: auto_correct_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auto_correct_rules (
    id integer NOT NULL,
    misspelled_word text,
    corrected_word text,
    is_active boolean,
    description text,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    created_by character varying(36)
);


--
-- Name: auto_correct_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.auto_correct_rules_id_seq
    START WITH 113
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: auto_correct_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.auto_correct_rules_id_seq OWNED BY public.auto_correct_rules.id;


--
-- Name: book_summaries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.book_summaries (
    book_id character varying(64) NOT NULL,
    summary text NOT NULL,
    embedding public.vector(768) NOT NULL,
    generated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: books; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.books (
    id text NOT NULL,
    content_hash character varying(64) NOT NULL,
    title text NOT NULL,
    author text,
    volume integer,
    total_pages integer DEFAULT 0 NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    upload_date timestamp with time zone DEFAULT now(),
    last_updated timestamp with time zone DEFAULT now(),
    updated_by text,
    created_by text,
    cover_url text,
    visibility character varying(20) DEFAULT 'private'::character varying,
    categories text[] DEFAULT '{}'::text[],
    last_error text,
    file_name text,
    source text,
    read_count integer DEFAULT 0 NOT NULL,
    pipeline_step character varying(20),
    file_type character varying(10) DEFAULT 'pdf'::character varying NOT NULL,
    ocr_milestone character varying(20) DEFAULT 'idle'::character varying NOT NULL,
    chunking_milestone character varying(20) DEFAULT 'idle'::character varying NOT NULL,
    embedding_milestone character varying(20) DEFAULT 'idle'::character varying NOT NULL,
    spell_check_milestone character varying(20) DEFAULT 'idle'::character varying NOT NULL,
    CONSTRAINT books_chunking_milestone_check CHECK (((chunking_milestone)::text = ANY ((ARRAY['idle'::character varying, 'in_progress'::character varying, 'complete'::character varying, 'partial_failure'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT books_embedding_milestone_check CHECK (((embedding_milestone)::text = ANY ((ARRAY['idle'::character varying, 'in_progress'::character varying, 'complete'::character varying, 'partial_failure'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT books_ocr_milestone_check CHECK (((ocr_milestone)::text = ANY ((ARRAY['idle'::character varying, 'in_progress'::character varying, 'complete'::character varying, 'partial_failure'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT books_spell_check_milestone_check CHECK (((spell_check_milestone)::text = ANY ((ARRAY['idle'::character varying, 'in_progress'::character varying, 'complete'::character varying, 'partial_failure'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT books_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'ocr_processing'::character varying, 'ocr_done'::character varying, 'indexing'::character varying, 'ready'::character varying, 'error'::character varying])::text[])))
);


--
-- Name: COLUMN books.ocr_milestone; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.books.ocr_milestone IS 'Book-level OCR milestone status (denormalized from pages)';


--
-- Name: COLUMN books.chunking_milestone; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.books.chunking_milestone IS 'Book-level chunking milestone status (denormalized from pages)';


--
-- Name: COLUMN books.embedding_milestone; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.books.embedding_milestone IS 'Book-level embedding milestone status (denormalized from pages)';


--
-- Name: COLUMN books.spell_check_milestone; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.books.spell_check_milestone IS 'Book-level spell check milestone status (denormalized from pages)';


--
-- Name: chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chunks (
    id bigint NOT NULL,
    book_id text NOT NULL,
    page_number integer NOT NULL,
    chunk_index integer DEFAULT 0 NOT NULL,
    text text NOT NULL,
    embedding public.vector(768),
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: chunks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chunks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chunks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chunks_id_seq OWNED BY public.chunks.id;


--
-- Name: contact_submissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contact_submissions (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    email character varying(255) NOT NULL,
    interest character varying(50) NOT NULL,
    message text NOT NULL,
    status character varying(20) DEFAULT 'new'::character varying NOT NULL,
    admin_notes text,
    reviewed_by character varying(36),
    reviewed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT contact_submissions_interest_check CHECK (((interest)::text = ANY ((ARRAY['editor'::character varying, 'developer'::character varying, 'other'::character varying])::text[]))),
    CONSTRAINT contact_submissions_status_check CHECK (((status)::text = ANY ((ARRAY['new'::character varying, 'reviewed'::character varying, 'contacted'::character varying, 'archived'::character varying])::text[])))
);


--
-- Name: contact_submissions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.contact_submissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: contact_submissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.contact_submissions_id_seq OWNED BY public.contact_submissions.id;


--
-- Name: dictionary; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dictionary (
    id integer CONSTRAINT words_id_not_null NOT NULL,
    word character varying(255) CONSTRAINT words_word_not_null NOT NULL
);


--
-- Name: dictionary_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dictionary_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dictionary_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dictionary_id_seq OWNED BY public.dictionary.id;


--
-- Name: page_spell_issues; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.page_spell_issues (
    id integer NOT NULL,
    page_id integer NOT NULL,
    word text NOT NULL,
    char_offset integer,
    char_end integer,
    status text DEFAULT 'open'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    ocr_corrections text[] DEFAULT '{}'::text[] NOT NULL,
    auto_corrected_at timestamp with time zone,
    claimed_at timestamp with time zone,
    CONSTRAINT page_spell_issues_status_check CHECK ((status = ANY (ARRAY['open'::text, 'corrected'::text, 'ignored'::text, 'processing'::text])))
);


--
-- Name: page_spell_issues_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.page_spell_issues_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: page_spell_issues_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.page_spell_issues_id_seq OWNED BY public.page_spell_issues.id;


--
-- Name: pages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pages (
    id bigint NOT NULL,
    book_id text NOT NULL,
    page_number integer NOT NULL,
    text text,
    status character varying(20) DEFAULT 'pending'::character varying,
    error text,
    last_updated timestamp with time zone DEFAULT now(),
    updated_by text,
    is_indexed boolean DEFAULT false,
    pipeline_step character varying(20),
    milestone character varying(20),
    retry_count integer DEFAULT 0 CONSTRAINT pages_v2_retry_count_not_null NOT NULL,
    spell_check_milestone text DEFAULT 'idle'::text,
    ocr_milestone character varying(20) DEFAULT 'idle'::character varying NOT NULL,
    chunking_milestone character varying(20) DEFAULT 'idle'::character varying NOT NULL,
    embedding_milestone character varying(20) DEFAULT 'idle'::character varying NOT NULL,
    CONSTRAINT pages_spell_check_milestone_check CHECK ((spell_check_milestone = ANY (ARRAY['idle'::text, 'in_progress'::text, 'done'::text, 'skipped'::text, 'failed'::text, 'error'::text]))),
    CONSTRAINT pages_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'ocr_processing'::character varying, 'ocr_done'::character varying, 'chunked'::character varying, 'indexing'::character varying, 'indexed'::character varying, 'error'::character varying])::text[])))
);


--
-- Name: COLUMN pages.ocr_milestone; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pages.ocr_milestone IS 'Milestone for the OCR stage';


--
-- Name: COLUMN pages.chunking_milestone; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pages.chunking_milestone IS 'Milestone for the text chunking stage';


--
-- Name: COLUMN pages.embedding_milestone; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pages.embedding_milestone IS 'Milestone for the vector embedding stage';


--
-- Name: pages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pages_id_seq OWNED BY public.pages.id;


--
-- Name: pipeline_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pipeline_events (
    id integer NOT NULL,
    page_id integer NOT NULL,
    event_type character varying(50) NOT NULL,
    payload text,
    processed boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: TABLE pipeline_events; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.pipeline_events IS 'Transactional outbox for pipeline state transitions and event-driven triggers';


--
-- Name: pipeline_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pipeline_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pipeline_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pipeline_events_id_seq OWNED BY public.pipeline_events.id;


--
-- Name: proverbs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.proverbs (
    id integer NOT NULL,
    text text NOT NULL,
    volume integer,
    page_number integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: proverbs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.proverbs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: proverbs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.proverbs_id_seq OWNED BY public.proverbs.id;


--
-- Name: rag_evaluations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rag_evaluations (
    id integer NOT NULL,
    book_id character varying(64),
    is_global boolean DEFAULT false NOT NULL,
    question text NOT NULL,
    current_page integer,
    retrieved_count integer DEFAULT 0 NOT NULL,
    context_chars integer DEFAULT 0 NOT NULL,
    scores double precision[],
    category_filter text[] DEFAULT '{}'::text[] NOT NULL,
    latency_ms integer DEFAULT 0 NOT NULL,
    answer_chars integer DEFAULT 0 NOT NULL,
    ts timestamp with time zone DEFAULT now() NOT NULL,
    user_id character varying(36)
);


--
-- Name: rag_evaluations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rag_evaluations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rag_evaluations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rag_evaluations_id_seq OWNED BY public.rag_evaluations.id;


--
-- Name: refresh_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.refresh_tokens (
    jti text NOT NULL,
    user_id text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    token_hash text DEFAULT ''::text NOT NULL,
    revoked boolean DEFAULT false NOT NULL,
    device_info text
);


--
-- Name: system_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_configs (
    key character varying(100) NOT NULL,
    value text NOT NULL,
    description text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: user_chat_usage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_chat_usage (
    id integer NOT NULL,
    user_id character varying(36) NOT NULL,
    usage_date date DEFAULT CURRENT_DATE NOT NULL,
    count integer DEFAULT 1 NOT NULL
);


--
-- Name: user_chat_usage_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_chat_usage_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_chat_usage_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_chat_usage_id_seq OWNED BY public.user_chat_usage.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id text NOT NULL,
    email character varying(255) NOT NULL,
    display_name text,
    avatar_url text,
    provider character varying(50),
    provider_id character varying(255),
    role character varying(20) DEFAULT 'reader'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    last_login_at timestamp with time zone,
    is_active boolean DEFAULT true,
    last_login_ip character varying(45)
);


--
-- Name: auto_correct_rules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auto_correct_rules ALTER COLUMN id SET DEFAULT nextval('public.auto_correct_rules_id_seq'::regclass);


--
-- Name: chunks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunks ALTER COLUMN id SET DEFAULT nextval('public.chunks_id_seq'::regclass);


--
-- Name: contact_submissions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contact_submissions ALTER COLUMN id SET DEFAULT nextval('public.contact_submissions_id_seq'::regclass);


--
-- Name: dictionary id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dictionary ALTER COLUMN id SET DEFAULT nextval('public.dictionary_id_seq'::regclass);


--
-- Name: page_spell_issues id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.page_spell_issues ALTER COLUMN id SET DEFAULT nextval('public.page_spell_issues_id_seq'::regclass);


--
-- Name: pages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pages ALTER COLUMN id SET DEFAULT nextval('public.pages_id_seq'::regclass);


--
-- Name: pipeline_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_events ALTER COLUMN id SET DEFAULT nextval('public.pipeline_events_id_seq'::regclass);


--
-- Name: proverbs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proverbs ALTER COLUMN id SET DEFAULT nextval('public.proverbs_id_seq'::regclass);


--
-- Name: rag_evaluations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_evaluations ALTER COLUMN id SET DEFAULT nextval('public.rag_evaluations_id_seq'::regclass);


--
-- Name: user_chat_usage id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_chat_usage ALTER COLUMN id SET DEFAULT nextval('public.user_chat_usage_id_seq'::regclass);


--
-- Name: auto_correct_rules auto_correct_rules_misspelled_word_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auto_correct_rules
    ADD CONSTRAINT auto_correct_rules_misspelled_word_key UNIQUE (misspelled_word);


--
-- Name: auto_correct_rules auto_correct_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auto_correct_rules
    ADD CONSTRAINT auto_correct_rules_pkey PRIMARY KEY (id);


--
-- Name: book_summaries book_summaries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.book_summaries
    ADD CONSTRAINT book_summaries_pkey PRIMARY KEY (book_id);


--
-- Name: books books_content_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.books
    ADD CONSTRAINT books_content_hash_key UNIQUE (content_hash);


--
-- Name: books books_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.books
    ADD CONSTRAINT books_pkey PRIMARY KEY (id);


--
-- Name: chunks chunks_book_id_page_number_chunk_index_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_book_id_page_number_chunk_index_key UNIQUE (book_id, page_number, chunk_index);


--
-- Name: chunks chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_pkey PRIMARY KEY (id);


--
-- Name: contact_submissions contact_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contact_submissions
    ADD CONSTRAINT contact_submissions_pkey PRIMARY KEY (id);


--
-- Name: dictionary dictionary_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dictionary
    ADD CONSTRAINT dictionary_pkey PRIMARY KEY (id);


--
-- Name: dictionary dictionary_word_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dictionary
    ADD CONSTRAINT dictionary_word_key UNIQUE (word);


--
-- Name: page_spell_issues page_spell_issues_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.page_spell_issues
    ADD CONSTRAINT page_spell_issues_pkey PRIMARY KEY (id);


--
-- Name: pages pages_book_id_page_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_book_id_page_number_key UNIQUE (book_id, page_number);


--
-- Name: pages pages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_pkey PRIMARY KEY (id);


--
-- Name: pipeline_events pipeline_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_events
    ADD CONSTRAINT pipeline_events_pkey PRIMARY KEY (id);


--
-- Name: proverbs proverbs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proverbs
    ADD CONSTRAINT proverbs_pkey PRIMARY KEY (id);


--
-- Name: rag_evaluations rag_evaluations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_evaluations
    ADD CONSTRAINT rag_evaluations_pkey PRIMARY KEY (id);


--
-- Name: refresh_tokens refresh_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_pkey PRIMARY KEY (jti);


--
-- Name: system_configs system_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_configs
    ADD CONSTRAINT system_configs_pkey PRIMARY KEY (key);


--
-- Name: user_chat_usage user_chat_usage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_chat_usage
    ADD CONSTRAINT user_chat_usage_pkey PRIMARY KEY (id);


--
-- Name: user_chat_usage user_chat_usage_user_id_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_chat_usage
    ADD CONSTRAINT user_chat_usage_user_id_date_key UNIQUE (user_id, usage_date);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_provider_provider_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_provider_provider_id_key UNIQUE (provider, provider_id);


--
-- Name: idx_book_summaries_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_book_summaries_embedding ON public.book_summaries USING ivfflat (embedding public.vector_cosine_ops) WITH (lists='50');


--
-- Name: idx_books_author_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_books_author_trgm ON public.books USING gin (author public.gin_trgm_ops);


--
-- Name: idx_books_categories_gin; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_books_categories_gin ON public.books USING gin (categories);


--
-- Name: idx_books_chunking_milestone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_books_chunking_milestone ON public.books USING btree (chunking_milestone) WHERE ((chunking_milestone)::text <> 'complete'::text);


--
-- Name: idx_books_embedding_milestone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_books_embedding_milestone ON public.books USING btree (embedding_milestone) WHERE ((embedding_milestone)::text <> 'complete'::text);


--
-- Name: idx_books_group_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_books_group_sort ON public.books USING btree (title, author, volume, upload_date DESC);


--
-- Name: idx_books_ocr_milestone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_books_ocr_milestone ON public.books USING btree (ocr_milestone) WHERE ((ocr_milestone)::text <> 'complete'::text);


--
-- Name: idx_books_read_count; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_books_read_count ON public.books USING btree (read_count DESC);


--
-- Name: idx_books_spell_check_milestone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_books_spell_check_milestone ON public.books USING btree (spell_check_milestone) WHERE ((spell_check_milestone)::text <> 'complete'::text);


--
-- Name: idx_books_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_books_status ON public.books USING btree (status);


--
-- Name: idx_books_status_visibility_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_books_status_visibility_date ON public.books USING btree (status, visibility, upload_date DESC);


--
-- Name: idx_books_title_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_books_title_trgm ON public.books USING gin (title public.gin_trgm_ops);


--
-- Name: idx_books_upload_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_books_upload_date ON public.books USING btree (upload_date DESC);


--
-- Name: idx_books_visibility_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_books_visibility_status ON public.books USING btree (visibility, status);


--
-- Name: idx_chunks_book_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chunks_book_id ON public.chunks USING btree (book_id);


--
-- Name: idx_chunks_book_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chunks_book_page ON public.chunks USING btree (book_id, page_number);


--
-- Name: idx_chunks_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chunks_embedding ON public.chunks USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='64');


--
-- Name: idx_contact_submissions_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_contact_submissions_created_at ON public.contact_submissions USING btree (created_at);


--
-- Name: idx_contact_submissions_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_contact_submissions_email ON public.contact_submissions USING btree (email);


--
-- Name: idx_contact_submissions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_contact_submissions_status ON public.contact_submissions USING btree (status);


--
-- Name: idx_page_spell_issues_auto_corrected; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_page_spell_issues_auto_corrected ON public.page_spell_issues USING btree (auto_corrected_at) WHERE (auto_corrected_at IS NOT NULL);


--
-- Name: idx_pages_book_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pages_book_id ON public.pages USING btree (book_id);


--
-- Name: idx_pages_book_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pages_book_page ON public.pages USING btree (book_id, page_number);


--
-- Name: idx_pages_chunking_milestone_failed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pages_chunking_milestone_failed ON public.pages USING btree (chunking_milestone) WHERE ((chunking_milestone)::text = ANY ((ARRAY['failed'::character varying, 'error'::character varying])::text[]));


--
-- Name: idx_pages_chunking_milestone_idle; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pages_chunking_milestone_idle ON public.pages USING btree (chunking_milestone) WHERE ((chunking_milestone)::text = 'idle'::text);


--
-- Name: idx_pages_embedding_milestone_failed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pages_embedding_milestone_failed ON public.pages USING btree (embedding_milestone) WHERE ((embedding_milestone)::text = ANY ((ARRAY['failed'::character varying, 'error'::character varying])::text[]));


--
-- Name: idx_pages_embedding_milestone_idle; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pages_embedding_milestone_idle ON public.pages USING btree (embedding_milestone) WHERE ((embedding_milestone)::text = 'idle'::text);


--
-- Name: idx_pages_ocr_milestone_failed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pages_ocr_milestone_failed ON public.pages USING btree (ocr_milestone) WHERE ((ocr_milestone)::text = ANY ((ARRAY['failed'::character varying, 'error'::character varying])::text[]));


--
-- Name: idx_pages_ocr_milestone_idle; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pages_ocr_milestone_idle ON public.pages USING btree (ocr_milestone) WHERE ((ocr_milestone)::text = 'idle'::text);


--
-- Name: idx_pages_retry_count_low; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pages_retry_count_low ON public.pages USING btree (retry_count) WHERE (retry_count < 3);


--
-- Name: idx_pages_spell_check_milestone_failed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pages_spell_check_milestone_failed ON public.pages USING btree (spell_check_milestone) WHERE (spell_check_milestone = ANY (ARRAY['failed'::text, 'error'::text]));


--
-- Name: idx_pages_spell_check_milestone_idle; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pages_spell_check_milestone_idle ON public.pages USING btree (spell_check_milestone) WHERE (spell_check_milestone = 'idle'::text);


--
-- Name: idx_pages_spell_check_milestone_incomplete; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pages_spell_check_milestone_incomplete ON public.pages USING btree (spell_check_milestone) WHERE (spell_check_milestone = ANY (ARRAY['idle'::text, 'in_progress'::text, 'failed'::text, 'error'::text]));


--
-- Name: idx_pages_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pages_status ON public.pages USING btree (status);


--
-- Name: idx_pipeline_events_page_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_events_page_id ON public.pipeline_events USING btree (page_id);


--
-- Name: idx_pipeline_events_processed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_events_processed ON public.pipeline_events USING btree (processed) WHERE (processed = false);


--
-- Name: idx_proverbs_text; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_proverbs_text ON public.proverbs USING btree (text);


--
-- Name: idx_proverbs_text_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_proverbs_text_trgm ON public.proverbs USING gin (text public.gin_trgm_ops);


--
-- Name: idx_rag_evaluations_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_evaluations_ts ON public.rag_evaluations USING btree (ts);


--
-- Name: idx_refresh_tokens_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_refresh_tokens_expires ON public.refresh_tokens USING btree (expires_at);


--
-- Name: idx_refresh_tokens_jti_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_refresh_tokens_jti_hash ON public.refresh_tokens USING btree (jti, token_hash) WHERE (NOT revoked);


--
-- Name: idx_refresh_tokens_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_refresh_tokens_token_hash ON public.refresh_tokens USING btree (token_hash) WHERE (NOT revoked);


--
-- Name: idx_refresh_tokens_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_refresh_tokens_user_id ON public.refresh_tokens USING btree (user_id);


--
-- Name: idx_spell_issues_open; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spell_issues_open ON public.page_spell_issues USING btree (page_id) WHERE (status = 'open'::text);


--
-- Name: idx_spell_issues_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spell_issues_page ON public.page_spell_issues USING btree (page_id);


--
-- Name: idx_spell_issues_page_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spell_issues_page_status ON public.page_spell_issues USING btree (page_id, status);


--
-- Name: idx_spell_issues_page_status_covering; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spell_issues_page_status_covering ON public.page_spell_issues USING btree (page_id, status) WHERE (status = 'open'::text);


--
-- Name: idx_spell_issues_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spell_issues_status ON public.page_spell_issues USING btree (status);


--
-- Name: idx_user_chat_usage_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_chat_usage_lookup ON public.user_chat_usage USING btree (user_id, usage_date);


--
-- Name: idx_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_email ON public.users USING btree (email);


--
-- Name: idx_users_provider; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_provider ON public.users USING btree (provider, provider_id);


--
-- Name: idx_users_provider_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_users_provider_id ON public.users USING btree (provider, provider_id);


--
-- Name: idx_users_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_role ON public.users USING btree (role);


--
-- Name: idx_words_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_words_trgm ON public.dictionary USING gin (word public.gin_trgm_ops);


--
-- Name: ix_auto_correct_rules_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auto_correct_rules_is_active ON public.auto_correct_rules USING btree (is_active);


--
-- Name: ix_auto_correct_rules_misspelled_word; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auto_correct_rules_misspelled_word ON public.auto_correct_rules USING btree (misspelled_word);


--
-- Name: ix_user_chat_usage_usage_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_chat_usage_usage_date ON public.user_chat_usage USING btree (usage_date);


--
-- Name: ix_user_chat_usage_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_chat_usage_user_id ON public.user_chat_usage USING btree (user_id);


--
-- Name: auto_correct_rules auto_correct_rules_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auto_correct_rules
    ADD CONSTRAINT auto_correct_rules_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: book_summaries book_summaries_book_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.book_summaries
    ADD CONSTRAINT book_summaries_book_id_fkey FOREIGN KEY (book_id) REFERENCES public.books(id) ON DELETE CASCADE;


--
-- Name: chunks chunks_book_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_book_id_fkey FOREIGN KEY (book_id) REFERENCES public.books(id) ON DELETE CASCADE;


--
-- Name: page_spell_issues page_spell_issues_page_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.page_spell_issues
    ADD CONSTRAINT page_spell_issues_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id) ON DELETE CASCADE;


--
-- Name: pages pages_book_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_book_id_fkey FOREIGN KEY (book_id) REFERENCES public.books(id) ON DELETE CASCADE;


--
-- Name: pipeline_events pipeline_events_page_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_events
    ADD CONSTRAINT pipeline_events_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id) ON DELETE CASCADE;


--
-- Name: rag_evaluations rag_evaluations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_evaluations
    ADD CONSTRAINT rag_evaluations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: refresh_tokens refresh_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_chat_usage user_chat_usage_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_chat_usage
    ADD CONSTRAINT user_chat_usage_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict hh82hcpfJu1AkKm0bCOaecdvnMK8OmhXNIoCkMjdimTYTMDBgrvKMDjkfp64RAJ

SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: system_configs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.system_configs (key, value, description, updated_at) FROM stdin;
chat_limit_reader	20	Daily chat limit for readers	2026-02-17 16:01:50.301984-06
auto_correct_batch_size	500	Maximum number of pages to auto-correct per job	2026-03-15 08:54:58.805845-05
gcs_auto_ocr_enabled	true	Whether to automatically start OCR for books discovered via GCS sync	2026-02-18 22:04:14.598605-06
chat_limit_editor	100	Daily chat limit for editors	2026-02-22 23:42:54.978609-06
gcs_auto_sync_interval_minutes	5	Interval in minutes for automated GCS bucket discovery	2026-02-18 21:50:48.174795-06
pdf_processing_enabled	true	Enable or disable PDF processing system-wide (true/false)	2026-02-20 08:28:07.304774-06
batch_ocr_retry_after	1772292775.4632232	Unix timestamp after which OCR batch submission is allowed again. Set automatically on 429 quota errors. Google resets batch quotas every 24 hours.	2026-02-27 09:32:55.46905-06
gcs_last_sync_at	2026-02-28T14:41:47.488538+00:00	Timestamp of the last GCS book discovery sync	2026-02-28 08:41:10.903212-06
llm_cb_failure_threshold	10	Number of consecutive failures before opening circuit breaker	2026-02-18 23:54:20.709868-06
llm_cb_recovery_seconds	60	Seconds to wait before attempting recovery (half-open)	2026-02-18 23:54:20.709868-06
gemini_embedding_model	models/gemini-embedding-001	Gemini model used for generating embeddings for semantic search.	2026-03-16 00:00:44.248018-05
batch_submission_interval_minutes	2	How often (in minutes) the worker runs chunking and realtime embedding. Lower = faster processing.	2026-02-28 07:06:31.732581-06
batch_chunking_limit	1000	Maximum number of pages to chunk in one cycle	2026-02-28 07:06:31.742394-06
batch_books_per_submission	1	Number of books to process per OCR batch submission. Next book is only picked up after the previous batch job is done or failed.	2026-02-26 04:56:54.441399-06
batch_embedding_limit	2000	Maximum number of chunks per embedding batch job	2026-02-28 07:06:31.744791-06
batch_submission_last_run_at	1772298205.6130502	Unix timestamp of the last time the submission cron ran. Managed automatically.	2026-02-28 11:03:25.612684-06
scanner_page_limit	100	Worker v2: Maximum pages claimed per chunking/embedding scanner run	2026-02-28 07:35:08.955512-06
maintenance_retention_days	7	Number of days to retain processed pipeline events before automated cleanup.	2026-03-11 21:42:01.50429-05
batch_last_polled_at	1772231700.613559	Unix timestamp of the last time the worker polled for batch jobs	2026-02-27 16:35:00.612787-06
batch_ocr_limit	1000	Maximum number of pages per OCR batch job	2026-02-25 21:11:18.125348-06
batch_polling_interval_minutes	5	How often (in minutes) the background worker polls Gemini for batch job updates	2026-02-25 21:11:18.125348-06
ocr_max_retry_count	10	Maximum number of OCR retry attempts per page before the page is skipped and marked as done	2026-02-26 23:28:56.731762-06
gemini_ocr_model	gemini-3.1-pro-preview	Gemini model used for OCR page processing.	2026-03-16 13:39:16.191062-05
gemini_chat_model	gemini-3-flash-preview	Gemini model used for chat responses (reader chat and global chat).	2026-03-16 13:44:30.231576-05
spell_check_enabled	true	Globally enable/disable background spell check processing.	2026-03-16 14:23:03.48184-05
scanner_book_limit	2	Worker v2: Maximum books dispatched per OCR scanner run	2026-03-14 18:43:22.492565-05
auto_correct_enabled	true	Enable automatic spell check corrections	2026-03-17 08:08:15.944047-05
gemini_categorization_model	gemini-3.1-flash-lite-preview	Gemini model used for category routing in global search.	2026-03-17 10:04:49.006415-05


--
-- PostgreSQL database dump complete
--


