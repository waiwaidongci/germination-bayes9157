-- Optional indexes for batch-level differential-privacy releases.
CREATE UNIQUE INDEX dp_release_id_idx ON dp_releases (release_id);
CREATE UNIQUE INDEX dp_release_token_idx ON dp_releases (token);
CREATE INDEX dp_release_source_idx ON dp_releases (source);
CREATE INDEX dp_release_study_idx ON dp_releases (study_id);
