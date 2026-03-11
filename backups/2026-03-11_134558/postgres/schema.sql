--
-- PostgreSQL database dump
--

\restrict tLg91BYDKMY7iCT8zWUEdwRa9qwv47cDWKwkyuzd49WvmKhfiYhTeKrosJfxIZU

-- Dumped from database version 16.13 (Debian 16.13-1.pgdg12+1)
-- Dumped by pg_dump version 16.13 (Debian 16.13-1.pgdg12+1)

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
-- Name: advice_tracking; Type: TABLE; Schema: public; Owner: helagent
--

CREATE TABLE public.advice_tracking (
    id integer NOT NULL,
    entry_id integer NOT NULL,
    advice_text text NOT NULL,
    category character varying(50),
    source_field character varying(50),
    user_feedback character varying(50),
    effectiveness_score integer,
    created_at timestamp with time zone NOT NULL
);


ALTER TABLE public.advice_tracking OWNER TO helagent;

--
-- Name: advice_tracking_id_seq; Type: SEQUENCE; Schema: public; Owner: helagent
--

CREATE SEQUENCE public.advice_tracking_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.advice_tracking_id_seq OWNER TO helagent;

--
-- Name: advice_tracking_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: helagent
--

ALTER SEQUENCE public.advice_tracking_id_seq OWNED BY public.advice_tracking.id;


--
-- Name: daily_advice; Type: TABLE; Schema: public; Owner: helagent
--

CREATE TABLE public.daily_advice (
    id integer NOT NULL,
    entry_id integer NOT NULL,
    model character varying(100),
    advice_json json,
    prompt_hash character varying(64),
    generated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.daily_advice OWNER TO helagent;

--
-- Name: daily_advice_id_seq; Type: SEQUENCE; Schema: public; Owner: helagent
--

CREATE SEQUENCE public.daily_advice_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.daily_advice_id_seq OWNER TO helagent;

--
-- Name: daily_advice_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: helagent
--

ALTER SEQUENCE public.daily_advice_id_seq OWNED BY public.daily_advice.id;


--
-- Name: daily_summaries; Type: TABLE; Schema: public; Owner: helagent
--

CREATE TABLE public.daily_summaries (
    id integer NOT NULL,
    entry_id integer NOT NULL,
    window_7d_json json,
    window_30d_json json,
    computed_at timestamp with time zone NOT NULL
);


ALTER TABLE public.daily_summaries OWNER TO helagent;

--
-- Name: daily_summaries_id_seq; Type: SEQUENCE; Schema: public; Owner: helagent
--

CREATE SEQUENCE public.daily_summaries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.daily_summaries_id_seq OWNER TO helagent;

--
-- Name: daily_summaries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: helagent
--

ALTER SEQUENCE public.daily_summaries_id_seq OWNED BY public.daily_summaries.id;


--
-- Name: health_entries; Type: TABLE; Schema: public; Owner: helagent
--

CREATE TABLE public.health_entries (
    id integer NOT NULL,
    user_id uuid NOT NULL,
    entry_date date NOT NULL,
    timezone_id character varying(50),
    created_at timestamp with time zone NOT NULL,
    synced_at timestamp with time zone NOT NULL,
    android_id integer
);


ALTER TABLE public.health_entries OWNER TO helagent;

--
-- Name: health_entries_id_seq; Type: SEQUENCE; Schema: public; Owner: helagent
--

CREATE SEQUENCE public.health_entries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.health_entries_id_seq OWNER TO helagent;

--
-- Name: health_entries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: helagent
--

ALTER SEQUENCE public.health_entries_id_seq OWNED BY public.health_entries.id;


--
-- Name: insight_reports; Type: TABLE; Schema: public; Owner: helagent
--

CREATE TABLE public.insight_reports (
    id integer NOT NULL,
    user_id uuid NOT NULL,
    week_start_date date NOT NULL,
    week_end_date date NOT NULL,
    ai_result_json json,
    status character varying(20) NOT NULL,
    error_message text,
    generated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.insight_reports OWNER TO helagent;

--
-- Name: insight_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: helagent
--

CREATE SEQUENCE public.insight_reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.insight_reports_id_seq OWNER TO helagent;

--
-- Name: insight_reports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: helagent
--

ALTER SEQUENCE public.insight_reports_id_seq OWNED BY public.insight_reports.id;


--
-- Name: medication_courses; Type: TABLE; Schema: public; Owner: helagent
--

CREATE TABLE public.medication_courses (
    id integer NOT NULL,
    med_id integer NOT NULL,
    start_date date NOT NULL,
    end_date date,
    status character varying(20) NOT NULL,
    frequency_text character varying(100),
    dose_text character varying(100),
    time_hints character varying(100),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.medication_courses OWNER TO helagent;

--
-- Name: medication_courses_id_seq; Type: SEQUENCE; Schema: public; Owner: helagent
--

CREATE SEQUENCE public.medication_courses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.medication_courses_id_seq OWNER TO helagent;

--
-- Name: medication_courses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: helagent
--

ALTER SEQUENCE public.medication_courses_id_seq OWNED BY public.medication_courses.id;


--
-- Name: medication_events; Type: TABLE; Schema: public; Owner: helagent
--

CREATE TABLE public.medication_events (
    id integer NOT NULL,
    user_id uuid NOT NULL,
    raw_text text NOT NULL,
    detected_med_names_json json,
    proposed_actions_json json,
    confirmed_actions_json json,
    apply_result character varying(200),
    created_at timestamp with time zone NOT NULL
);


ALTER TABLE public.medication_events OWNER TO helagent;

--
-- Name: medication_events_id_seq; Type: SEQUENCE; Schema: public; Owner: helagent
--

CREATE SEQUENCE public.medication_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.medication_events_id_seq OWNER TO helagent;

--
-- Name: medication_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: helagent
--

ALTER SEQUENCE public.medication_events_id_seq OWNED BY public.medication_events.id;


--
-- Name: medication_reminders; Type: TABLE; Schema: public; Owner: helagent
--

CREATE TABLE public.medication_reminders (
    id integer NOT NULL,
    med_id integer NOT NULL,
    hour integer NOT NULL,
    minute integer NOT NULL,
    repeat_type character varying(20) NOT NULL,
    week_days character varying(50),
    enabled boolean NOT NULL
);


ALTER TABLE public.medication_reminders OWNER TO helagent;

--
-- Name: medication_reminders_id_seq; Type: SEQUENCE; Schema: public; Owner: helagent
--

CREATE SEQUENCE public.medication_reminders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.medication_reminders_id_seq OWNER TO helagent;

--
-- Name: medication_reminders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: helagent
--

ALTER SEQUENCE public.medication_reminders_id_seq OWNED BY public.medication_reminders.id;


--
-- Name: medications; Type: TABLE; Schema: public; Owner: helagent
--

CREATE TABLE public.medications (
    id integer NOT NULL,
    user_id uuid NOT NULL,
    name character varying(200) NOT NULL,
    aliases text,
    note text,
    info_summary text,
    image_uri character varying(500),
    android_id integer,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.medications OWNER TO helagent;

--
-- Name: medications_id_seq; Type: SEQUENCE; Schema: public; Owner: helagent
--

CREATE SEQUENCE public.medications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.medications_id_seq OWNER TO helagent;

--
-- Name: medications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: helagent
--

ALTER SEQUENCE public.medications_id_seq OWNED BY public.medications.id;


--
-- Name: memory_entries; Type: TABLE; Schema: public; Owner: helagent
--

CREATE TABLE public.memory_entries (
    id integer NOT NULL,
    user_id uuid NOT NULL,
    memory_type character varying(50) NOT NULL,
    content text NOT NULL,
    importance_score double precision NOT NULL,
    embedding double precision[],
    created_at timestamp with time zone NOT NULL,
    last_accessed_at timestamp with time zone NOT NULL,
    metadata_json text
);


ALTER TABLE public.memory_entries OWNER TO helagent;

--
-- Name: memory_entries_id_seq; Type: SEQUENCE; Schema: public; Owner: helagent
--

CREATE SEQUENCE public.memory_entries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.memory_entries_id_seq OWNER TO helagent;

--
-- Name: memory_entries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: helagent
--

ALTER SEQUENCE public.memory_entries_id_seq OWNED BY public.memory_entries.id;


--
-- Name: question_responses; Type: TABLE; Schema: public; Owner: helagent
--

CREATE TABLE public.question_responses (
    id integer NOT NULL,
    entry_id integer NOT NULL,
    question_id character varying(100) NOT NULL,
    step_index integer NOT NULL,
    answer_type character varying(50) NOT NULL,
    answer_value text,
    answer_label text,
    metadata_json json
);


ALTER TABLE public.question_responses OWNER TO helagent;

--
-- Name: question_responses_id_seq; Type: SEQUENCE; Schema: public; Owner: helagent
--

CREATE SEQUENCE public.question_responses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.question_responses_id_seq OWNER TO helagent;

--
-- Name: question_responses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: helagent
--

ALTER SEQUENCE public.question_responses_id_seq OWNED BY public.question_responses.id;


--
-- Name: sync_tombstones; Type: TABLE; Schema: public; Owner: helagent
--

CREATE TABLE public.sync_tombstones (
    id integer NOT NULL,
    user_id uuid NOT NULL,
    entity character varying(50) NOT NULL,
    record_id integer NOT NULL,
    payload_json json,
    deleted_at timestamp with time zone NOT NULL
);


ALTER TABLE public.sync_tombstones OWNER TO helagent;

--
-- Name: sync_tombstones_id_seq; Type: SEQUENCE; Schema: public; Owner: helagent
--

CREATE SEQUENCE public.sync_tombstones_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sync_tombstones_id_seq OWNER TO helagent;

--
-- Name: sync_tombstones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: helagent
--

ALTER SEQUENCE public.sync_tombstones_id_seq OWNED BY public.sync_tombstones.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: helagent
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    username character varying(50) NOT NULL,
    email character varying(255) NOT NULL,
    hashed_password character varying(255) NOT NULL,
    display_name character varying(100),
    is_active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.users OWNER TO helagent;

--
-- Name: advice_tracking id; Type: DEFAULT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.advice_tracking ALTER COLUMN id SET DEFAULT nextval('public.advice_tracking_id_seq'::regclass);


--
-- Name: daily_advice id; Type: DEFAULT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.daily_advice ALTER COLUMN id SET DEFAULT nextval('public.daily_advice_id_seq'::regclass);


--
-- Name: daily_summaries id; Type: DEFAULT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.daily_summaries ALTER COLUMN id SET DEFAULT nextval('public.daily_summaries_id_seq'::regclass);


--
-- Name: health_entries id; Type: DEFAULT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.health_entries ALTER COLUMN id SET DEFAULT nextval('public.health_entries_id_seq'::regclass);


--
-- Name: insight_reports id; Type: DEFAULT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.insight_reports ALTER COLUMN id SET DEFAULT nextval('public.insight_reports_id_seq'::regclass);


--
-- Name: medication_courses id; Type: DEFAULT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.medication_courses ALTER COLUMN id SET DEFAULT nextval('public.medication_courses_id_seq'::regclass);


--
-- Name: medication_events id; Type: DEFAULT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.medication_events ALTER COLUMN id SET DEFAULT nextval('public.medication_events_id_seq'::regclass);


--
-- Name: medication_reminders id; Type: DEFAULT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.medication_reminders ALTER COLUMN id SET DEFAULT nextval('public.medication_reminders_id_seq'::regclass);


--
-- Name: medications id; Type: DEFAULT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.medications ALTER COLUMN id SET DEFAULT nextval('public.medications_id_seq'::regclass);


--
-- Name: memory_entries id; Type: DEFAULT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.memory_entries ALTER COLUMN id SET DEFAULT nextval('public.memory_entries_id_seq'::regclass);


--
-- Name: question_responses id; Type: DEFAULT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.question_responses ALTER COLUMN id SET DEFAULT nextval('public.question_responses_id_seq'::regclass);


--
-- Name: sync_tombstones id; Type: DEFAULT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.sync_tombstones ALTER COLUMN id SET DEFAULT nextval('public.sync_tombstones_id_seq'::regclass);


--
-- Name: advice_tracking advice_tracking_pkey; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.advice_tracking
    ADD CONSTRAINT advice_tracking_pkey PRIMARY KEY (id);


--
-- Name: daily_advice daily_advice_pkey; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.daily_advice
    ADD CONSTRAINT daily_advice_pkey PRIMARY KEY (id);


--
-- Name: daily_summaries daily_summaries_pkey; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.daily_summaries
    ADD CONSTRAINT daily_summaries_pkey PRIMARY KEY (id);


--
-- Name: health_entries health_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.health_entries
    ADD CONSTRAINT health_entries_pkey PRIMARY KEY (id);


--
-- Name: insight_reports insight_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.insight_reports
    ADD CONSTRAINT insight_reports_pkey PRIMARY KEY (id);


--
-- Name: medication_courses medication_courses_pkey; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.medication_courses
    ADD CONSTRAINT medication_courses_pkey PRIMARY KEY (id);


--
-- Name: medication_events medication_events_pkey; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.medication_events
    ADD CONSTRAINT medication_events_pkey PRIMARY KEY (id);


--
-- Name: medication_reminders medication_reminders_pkey; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.medication_reminders
    ADD CONSTRAINT medication_reminders_pkey PRIMARY KEY (id);


--
-- Name: medications medications_pkey; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.medications
    ADD CONSTRAINT medications_pkey PRIMARY KEY (id);


--
-- Name: memory_entries memory_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.memory_entries
    ADD CONSTRAINT memory_entries_pkey PRIMARY KEY (id);


--
-- Name: question_responses question_responses_pkey; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.question_responses
    ADD CONSTRAINT question_responses_pkey PRIMARY KEY (id);


--
-- Name: sync_tombstones sync_tombstones_pkey; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.sync_tombstones
    ADD CONSTRAINT sync_tombstones_pkey PRIMARY KEY (id);


--
-- Name: daily_advice uq_daily_advice_entry; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.daily_advice
    ADD CONSTRAINT uq_daily_advice_entry UNIQUE (entry_id);


--
-- Name: daily_summaries uq_daily_summary_entry; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.daily_summaries
    ADD CONSTRAINT uq_daily_summary_entry UNIQUE (entry_id);


--
-- Name: health_entries uq_user_entry_date; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.health_entries
    ADD CONSTRAINT uq_user_entry_date UNIQUE (user_id, entry_date);


--
-- Name: insight_reports uq_user_week_insight; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.insight_reports
    ADD CONSTRAINT uq_user_week_insight UNIQUE (user_id, week_start_date);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_advice_tracking_entry_id; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_advice_tracking_entry_id ON public.advice_tracking USING btree (entry_id);


--
-- Name: ix_daily_advice_entry_id; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_daily_advice_entry_id ON public.daily_advice USING btree (entry_id);


--
-- Name: ix_daily_summaries_entry_id; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_daily_summaries_entry_id ON public.daily_summaries USING btree (entry_id);


--
-- Name: ix_health_entries_entry_date; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_health_entries_entry_date ON public.health_entries USING btree (entry_date);


--
-- Name: ix_health_entries_user_id; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_health_entries_user_id ON public.health_entries USING btree (user_id);


--
-- Name: ix_insight_reports_user_id; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_insight_reports_user_id ON public.insight_reports USING btree (user_id);


--
-- Name: ix_medication_courses_med_id; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_medication_courses_med_id ON public.medication_courses USING btree (med_id);


--
-- Name: ix_medication_events_user_id; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_medication_events_user_id ON public.medication_events USING btree (user_id);


--
-- Name: ix_medication_reminders_med_id; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_medication_reminders_med_id ON public.medication_reminders USING btree (med_id);


--
-- Name: ix_medications_user_id; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_medications_user_id ON public.medications USING btree (user_id);


--
-- Name: ix_memory_entries_memory_type; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_memory_entries_memory_type ON public.memory_entries USING btree (memory_type);


--
-- Name: ix_memory_entries_user_id; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_memory_entries_user_id ON public.memory_entries USING btree (user_id);


--
-- Name: ix_question_responses_entry_id; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_question_responses_entry_id ON public.question_responses USING btree (entry_id);


--
-- Name: ix_sync_tombstones_deleted_at; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_sync_tombstones_deleted_at ON public.sync_tombstones USING btree (deleted_at);


--
-- Name: ix_sync_tombstones_entity; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_sync_tombstones_entity ON public.sync_tombstones USING btree (entity);


--
-- Name: ix_sync_tombstones_user_id; Type: INDEX; Schema: public; Owner: helagent
--

CREATE INDEX ix_sync_tombstones_user_id ON public.sync_tombstones USING btree (user_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: helagent
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_username; Type: INDEX; Schema: public; Owner: helagent
--

CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username);


--
-- Name: advice_tracking advice_tracking_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.advice_tracking
    ADD CONSTRAINT advice_tracking_entry_id_fkey FOREIGN KEY (entry_id) REFERENCES public.health_entries(id) ON DELETE CASCADE;


--
-- Name: daily_advice daily_advice_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.daily_advice
    ADD CONSTRAINT daily_advice_entry_id_fkey FOREIGN KEY (entry_id) REFERENCES public.health_entries(id) ON DELETE CASCADE;


--
-- Name: daily_summaries daily_summaries_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.daily_summaries
    ADD CONSTRAINT daily_summaries_entry_id_fkey FOREIGN KEY (entry_id) REFERENCES public.health_entries(id) ON DELETE CASCADE;


--
-- Name: health_entries health_entries_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.health_entries
    ADD CONSTRAINT health_entries_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: insight_reports insight_reports_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.insight_reports
    ADD CONSTRAINT insight_reports_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: medication_courses medication_courses_med_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.medication_courses
    ADD CONSTRAINT medication_courses_med_id_fkey FOREIGN KEY (med_id) REFERENCES public.medications(id) ON DELETE CASCADE;


--
-- Name: medication_events medication_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.medication_events
    ADD CONSTRAINT medication_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: medication_reminders medication_reminders_med_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.medication_reminders
    ADD CONSTRAINT medication_reminders_med_id_fkey FOREIGN KEY (med_id) REFERENCES public.medications(id) ON DELETE CASCADE;


--
-- Name: medications medications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.medications
    ADD CONSTRAINT medications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: memory_entries memory_entries_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.memory_entries
    ADD CONSTRAINT memory_entries_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: question_responses question_responses_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.question_responses
    ADD CONSTRAINT question_responses_entry_id_fkey FOREIGN KEY (entry_id) REFERENCES public.health_entries(id) ON DELETE CASCADE;


--
-- Name: sync_tombstones sync_tombstones_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: helagent
--

ALTER TABLE ONLY public.sync_tombstones
    ADD CONSTRAINT sync_tombstones_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict tLg91BYDKMY7iCT8zWUEdwRa9qwv47cDWKwkyuzd49WvmKhfiYhTeKrosJfxIZU

