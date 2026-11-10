IF DB_ID('PoluxImportDB') IS NULL
BEGIN
    PRINT 'Creating PoluxImportDB...';
    EXEC('CREATE DATABASE PoluxImportDB');
END
ELSE
BEGIN
    PRINT 'PoluxImportDB already exists.';
END
GO