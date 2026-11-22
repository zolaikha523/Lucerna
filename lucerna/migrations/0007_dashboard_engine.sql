-- Universal dashboard engine: workbook intelligence, sheet roles, dashboard themes/branding and linked sheets.
ALTER TABLE data_files ADD COLUMN workbook_json TEXT;          -- sheet classification, primary choice, relationships, explanation
ALTER TABLE datasets ADD COLUMN sheet_role TEXT;               -- survey | monitoring | sampling_frame | indicator_map | codebook | lookup | documentation | other_table
ALTER TABLE datasets ADD COLUMN sheet_role_json TEXT;          -- confidence and reasons
ALTER TABLE datasets ADD COLUMN is_primary INTEGER DEFAULT 0;  -- chosen as the main analytical sheet of its workbook
ALTER TABLE dashboards ADD COLUMN theme TEXT DEFAULT 'corporate';
ALTER TABLE dashboards ADD COLUMN branding_json TEXT;          -- title, subtitle, organisation display, logo
ALTER TABLE dashboards ADD COLUMN linked_json TEXT;            -- related dataset ids analysed alongside the main dataset
ALTER TABLE dashboards ADD COLUMN source_version INTEGER;      -- dataset version the dashboard was generated from
ALTER TABLE dashboards ADD COLUMN generated_at REAL;
