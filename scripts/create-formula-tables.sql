-- Formula Engine Database Schema
-- Run this script to create the required tables for the Formula Engine

-- 1. Formula Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Formula')
BEGIN
    CREATE TABLE Formula (
        id BIGINT PRIMARY KEY IDENTITY(1,1),
        name NVARCHAR(255) NOT NULL,
        expression NVARCHAR(MAX) NOT NULL,
        is_active BIT DEFAULT 1,
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE()
    );
    
    CREATE INDEX IX_Formula_IsActive ON Formula(is_active);
    PRINT 'Formula table created successfully';
END
ELSE
BEGIN
    PRINT 'Formula table already exists';
END
GO

-- 2. FormulaTagMapping Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'FormulaTagMapping')
BEGIN
    CREATE TABLE FormulaTagMapping (
        id BIGINT PRIMARY KEY IDENTITY(1,1),
        formula_id BIGINT NOT NULL,
        variable_name NVARCHAR(50) NOT NULL,
        tag_id BIGINT NOT NULL,
        FOREIGN KEY (formula_id) REFERENCES Formula(id) ON DELETE CASCADE,
        FOREIGN KEY (tag_id) REFERENCES TagRegistry(id)
    );
    
    CREATE INDEX IX_FormulaTagMapping_FormulaId ON FormulaTagMapping(formula_id);
    CREATE INDEX IX_FormulaTagMapping_TagId ON FormulaTagMapping(tag_id);
    CREATE UNIQUE INDEX IX_FormulaTagMapping_Unique ON FormulaTagMapping(formula_id, variable_name);
    PRINT 'FormulaTagMapping table created successfully';
END
ELSE
BEGIN
    PRINT 'FormulaTagMapping table already exists';
END
GO

-- 3. CalculatedTags Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'CalculatedTags')
BEGIN
    CREATE TABLE CalculatedTags (
        id BIGINT PRIMARY KEY IDENTITY(1,1),
        formula_id NVARCHAR(50) NOT NULL,
        result_value FLOAT NOT NULL,
        calculated_at DATETIME NOT NULL,
        execution_time_ms FLOAT NOT NULL,
        trigger_tag_id BIGINT NULL
    );
    
    CREATE INDEX IX_CalculatedTags_FormulaId ON CalculatedTags(formula_id);
    CREATE INDEX IX_CalculatedTags_CalculatedAt ON CalculatedTags(calculated_at);
    CREATE INDEX IX_CalculatedTags_FormulaId_CalculatedAt ON CalculatedTags(formula_id, calculated_at);
    PRINT 'CalculatedTags table created successfully';
END
ELSE
BEGIN
    PRINT 'CalculatedTags table already exists';
END
GO

PRINT 'Formula Engine schema setup complete!';
