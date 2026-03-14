INSERT INTO scrape_runs (id, company, status, started_at, finished_at, postings_found, error_message, attempt_number)
VALUES
    ('a0000000-0000-0000-0000-000000000001', 'anthropic', 'success', '2026-03-12 12:00:00+00', '2026-03-12 12:00:05+00', 3, NULL, 1),
    ('a0000000-0000-0000-0000-000000000002', 'openai', 'success', '2026-03-12 12:00:00+00', '2026-03-12 12:00:07+00', 2, NULL, 1),
    ('a0000000-0000-0000-0000-000000000003', 'deepmind', 'failed', '2026-03-12 12:00:00+00', '2026-03-12 12:00:10+00', NULL, 'TimeoutError: page load exceeded 30s', 1);

INSERT INTO job_postings (id, scrape_run_id, company, title, location, url, first_seen_date, last_seen_date, is_software_engineering)
VALUES
    ('b0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'anthropic', 'Senior Software Engineer', 'San Francisco', 'https://anthropic.com/swe-1', CURRENT_DATE - 1, CURRENT_DATE - 1, true),
    ('b0000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001', 'anthropic', 'Platform Engineer', 'Remote', 'https://anthropic.com/pe-1', CURRENT_DATE - 1, CURRENT_DATE - 1, true),
    ('b0000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000002', 'openai', 'Backend Engineer', 'San Francisco', 'https://openai.com/be-1', CURRENT_DATE - 1, CURRENT_DATE - 1, true),
    ('b0000000-0000-0000-0000-000000000004', 'a0000000-0000-0000-0000-000000000002', 'openai', 'Frontend Engineer', 'San Francisco', 'https://openai.com/fe-1', CURRENT_DATE - 1, CURRENT_DATE - 1, true);
