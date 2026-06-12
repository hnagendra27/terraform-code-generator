# Terraform Code Generator for Snowflake

A Streamlit application that automates generating Terraform HCL code and parent role files for provisioning Snowflake databases, schemas, roles, and access controls across DEV, QA, CERT, and PROD environments.

## Features

- **Role Creation** — Generates warehouse definitions, role definitions, warehouse privileges, downloadable parent role files, and database access assignments
- **Database Creation** — Generates database, schema, and account role definitions with downloadable parent role ZIP files for Source, Mixer, and Application database types

## Database Types

| Type | Suffix | Schemas |
|------|--------|---------|
| Source | `_SRC` | RAW, STAGING, CONFORMED |
| Mixer | (none) | STAGING, CONFORMED |
| Application | `_APP` | STAGING, CONFORMED, CONSUMPTION |

## How to Use

1. Select **Role Creation** or **Database Creation**
2. Fill in the required fields (name, environments, access entries)
3. Click **Generate Terraform Code**
4. Copy the generated HCL snippets into your `.tfvars` files
5. Download the parent role `.txt` files and place them in the appropriate environment folder

## Prerequisites

- Snowflake account with Streamlit enabled
- Appropriate role with workspace access

