--
-- PostgreSQL database dump
--

\restrict Nod5o0BVqfi5B26ZhSlsGq3KhZU4PLayINrxJaMrdDCt3gAFScbJbzkc9oYVdxr

-- Dumped from database version 15.17 (Debian 15.17-1.pgdg13+1)
-- Dumped by pg_dump version 15.17 (Debian 15.17-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: closing_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.closing_documents (
    id integer NOT NULL,
    purchase_id integer NOT NULL,
    doc_type character varying(50) NOT NULL,
    doc_number character varying(100),
    doc_date date,
    amount numeric(15,2),
    note character varying(500),
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: closing_documents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.closing_documents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: closing_documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.closing_documents_id_seq OWNED BY public.closing_documents.id;


--
-- Name: expense_directions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.expense_directions (
    id integer NOT NULL,
    name character varying(500),
    subsidy_id integer
);


--
-- Name: expense_directions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.expense_directions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: expense_directions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.expense_directions_id_seq OWNED BY public.expense_directions.id;


--
-- Name: idempotency_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.idempotency_keys (
    key character varying(128) NOT NULL,
    method character varying(10) NOT NULL,
    path character varying(500) NOT NULL,
    status_code integer NOT NULL,
    response_body text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL
);


--
-- Name: closing_documents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.closing_documents ALTER COLUMN id SET DEFAULT nextval('public.closing_documents_id_seq'::regclass);


--
-- Name: expense_directions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expense_directions ALTER COLUMN id SET DEFAULT nextval('public.expense_directions_id_seq'::regclass);


--
-- Name: closing_documents closing_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.closing_documents
    ADD CONSTRAINT closing_documents_pkey PRIMARY KEY (id);


--
-- Name: expense_directions expense_directions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expense_directions
    ADD CONSTRAINT expense_directions_pkey PRIMARY KEY (id);


--
-- Name: idempotency_keys idempotency_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_keys
    ADD CONSTRAINT idempotency_keys_pkey PRIMARY KEY (key);


--
-- Name: ix_closing_documents_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_closing_documents_id ON public.closing_documents USING btree (id);


--
-- Name: ix_closing_documents_purchase_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_closing_documents_purchase_id ON public.closing_documents USING btree (purchase_id);


--
-- Name: ix_idempotency_keys_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_idempotency_keys_expires_at ON public.idempotency_keys USING btree (expires_at);


--
-- Name: closing_documents closing_documents_purchase_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.closing_documents
    ADD CONSTRAINT closing_documents_purchase_id_fkey FOREIGN KEY (purchase_id) REFERENCES public.purchases(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict Nod5o0BVqfi5B26ZhSlsGq3KhZU4PLayINrxJaMrdDCt3gAFScbJbzkc9oYVdxr

