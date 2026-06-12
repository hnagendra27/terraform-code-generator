import streamlit as st
import io
import zipfile
import os
from datetime import datetime

conn = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL"))
session = conn.session()

_copy_counter = [0]

def code_with_copy(code_text, language="hcl"):
    _copy_counter[0] += 1
    st.code(code_text, language=language)
    st.button("📋 Copy", key=f"copy_{_copy_counter[0]}_{st.session_state.get('reset_counter', 0)}", on_click=_set_clipboard, args=(code_text,))

def _set_clipboard(text):
    st.session_state["_clipboard"] = text

st.title("Terraform Code Generator")

if "_clipboard" in st.session_state and st.session_state["_clipboard"]:
    st.toast("Copied to clipboard!")
    st.code(st.session_state["_clipboard"], language="hcl")
    st.session_state["_clipboard"] = ""

if "reset_counter" not in st.session_state:
    st.session_state.reset_counter = 0

if st.button("Reset All Fields"):
    st.session_state.reset_counter += 1
    st.session_state.db_access_list = []
    st.session_state.db_input_key = 0
    st.session_state.db_generated = False
    st.session_state.db_generated_data = {}
    st.rerun()

rc = st.session_state.reset_counter

st.write("Generate Terraform code for Snowflake resources.")

option = st.selectbox("What would you like to create?", ["Role Creation", "Database Creation"], key=f"option_{rc}")

if option == "Role Creation":
    st.subheader("Role Creation")
    role_name = st.text_input("Role Name", placeholder="e.g. RETENTION_INSIGHTS", key=f"role_name_{rc}")
    envs = st.multiselect("Environment(s)", ["DEV", "QA", "CERT", "PROD"], key=f"env_{rc}")

    st.subheader("Database Access")
    st.write("Add databases and schemas this role needs access to.")

    if "db_access_list" not in st.session_state:
        st.session_state.db_access_list = []

    if "db_input_key" not in st.session_state:
        st.session_state.db_input_key = 0

    with st.expander("Add Database Access", expanded=True):
        key_suffix = st.session_state.db_input_key
        db_name_input = st.text_input("Database Name", placeholder="e.g. ATLAS", key=f"db_{key_suffix}")
        schema_input = st.text_input("Schema Name", placeholder="e.g. PUBLIC", key=f"schema_{key_suffix}")
        access_type = st.selectbox("Access Type", ["READ_ONLY"], key=f"access_{key_suffix}")
        if st.button("Add Database"):
            if not db_name_input.strip():
                st.error("Please provide a database name.")
            elif not schema_input.strip():
                st.error("Please provide a schema name.")
            else:
                new_entry = {
                    "database": db_name_input.strip().upper(),
                    "schema": schema_input.strip().upper(),
                    "access": access_type
                }
                if new_entry in st.session_state.db_access_list:
                    st.warning("Already exists!")
                else:
                    st.session_state.db_access_list.append(new_entry)
                    st.session_state.db_input_key += 1
                    st.rerun()

    if st.session_state.db_access_list:
        st.write("**Current Access List:**")
        for i, entry in enumerate(st.session_state.db_access_list):
            st.write(f"- {entry['database']}.{entry['schema']} → {entry['access']}")
        if st.button("Clear All"):
            st.session_state.db_access_list = []
            st.rerun()

    if st.button("Generate Terraform Code"):
        if not role_name:
            st.error("Please provide a role name.")
        elif not envs:
            st.error("Please select at least one environment.")
        elif not st.session_state.db_access_list:
            st.error("Please add at least one database access entry.")
        else:
            role_upper = role_name.strip().upper().replace(" ", "_")
            role_lower = role_name.strip().lower().replace(" ", "_")
            wh_name = f"{role_upper}_WH"
            role_full = f"{role_upper}_ROLE"
            db_names = [e["database"] for e in st.session_state.db_access_list]
            unique_dbs = list(dict.fromkeys(db_names))
            db_list_str = ", ".join(unique_dbs)

            for env in envs:
                st.markdown("---")
                st.markdown(f"## Environment: {env}")

                st.markdown(f"### Step 1: Create {role_lower}_wh")
                st.markdown(f"Add to `{env.lower()}.tfvars`:")
                step1 = f"""{wh_name} = {{
  size    = "MEDIUM"
  comment = "Warehouse for {role_full} role and operations"
}}"""
                st.code(step1, language="hcl")

                st.markdown(f"### Step 2: Create {role_lower}_role")
                st.markdown(f"Add to `{env.lower()}.tfvars`:")
                step2 = f"""{role_full} = {{
  comment          = "Role for access to {db_list_str} and related objects"
  parent_role_file = "{role_full}.txt"
}}"""
                st.code(step2, language="hcl")

                st.markdown(f"### Step 3: Enable warehouse privileges")
                st.markdown(f"Add to `{env.lower()}.tfvars`:")
                step3 = f"""{role_full} = {{
  warehouse_privileges = {{
    {wh_name} = ["USAGE", "MONITOR"]
  }}
}}"""
                st.code(step3, language="hcl")

                st.markdown(f"### Step 4: Download parent role file for {env.lower()} folder")
                parent_file_content = "TERRAFORM_SYSADMIN_ROLE"
                st.download_button(
                    label=f"Download {role_full}.txt",
                    data=parent_file_content,
                    file_name=f"{role_full}.txt",
                    mime="text/plain",
                    key=f"parent_{role_full}_{env}_{rc}",
                )

                st.markdown(f"### Step 5: Add `{role_full}` in the following files")
                parent_role_files = []
                for entry in st.session_state.db_access_list:
                    schema_part = entry["schema"]
                    access_suffix = "READ_ONLY_ACCESS" if entry["access"] == "READ_ONLY" else "DDL_ACCESS"
                    filename = f"{entry['database']}_{schema_part}_{access_suffix}_ROLE.txt"
                    parent_role_files.append(filename)

                unique_files = list(dict.fromkeys(parent_role_files))
                for f in unique_files:
                    st.code(f, language="text")

elif option == "Database Creation":
    st.subheader("Database Creation")
    db_type = st.selectbox("Database Type", ["Source", "Mixer", "Application"], key=f"db_type_{rc}")
    envs_db = st.multiselect("Environment(s)", ["DEV", "QA", "CERT", "PROD"], key=f"db_env_{rc}")
    db_name = st.text_input("Database Name", placeholder="e.g. BFS", key=f"db_name_{rc}")

    if "db_generated" not in st.session_state:
        st.session_state.db_generated = False
        st.session_state.db_generated_data = {}

    if st.button("Generate Terraform Code"):
        if not db_name:
            st.error("Please provide a database name.")
        elif not envs_db:
            st.error("Please select at least one environment.")
        else:
            st.session_state.db_generated = True
            st.session_state.db_generated_data = {
                "db_name": db_name.strip().upper(),
                "db_type": db_type,
                "envs": envs_db,
            }
            st.rerun()

    if st.session_state.db_generated:
        data = st.session_state.db_generated_data
        db_upper = data["db_name"]
        db_type_val = data["db_type"]
        envs_gen = data["envs"]

        if db_type_val == "Source":
            if not db_upper.endswith("_SRC"):
                db_upper = f"{db_upper}_SRC"
            schemas = ["RAW", "STAGING", "CONFORMED"]
            num_roles = len(schemas) * 3
            num_files = num_roles

            st.markdown("---")
            st.subheader("Preview")
            st.info(f"**Database:** {db_upper}  \n**Schemas:** {', '.join(schemas)}  \n**Roles to create:** {num_roles}  \n**Parent role files:** {num_files}  \n**Environments:** {', '.join(envs_gen)}")

            ddl_contents = {
                "DEV": "OPENLAKEHOUSE_ANALYTICAL_ENGINEER_ROLE\n,CLOUD_COMPOSER_ROLE",
                "QA": "OPENLAKEHOUSE_QA_ENGINEER_ROLE\n,CLOUD_COMPOSER_ROLE",
                "CERT": "OPENLAKEHOUSE_UAT_ENGINEER_ROLE\n,CLOUD_COMPOSER_ROLE",
                "PROD": "OPENLAKEHOUSE_SUPPORT_ENGINEER_ROLE\n,CLOUD_COMPOSER_ROLE",
            }

            for env in envs_gen:
                st.markdown("---")
                st.markdown(f"## Environment: {env}")

                st.markdown(f"### Step 1: Add database under snowflake_database section in `{env.lower()}.tfvars`")
                step1 = f"""{db_upper} = {{
  comment = "Source System db"
}}"""
                code_with_copy(step1)

                st.markdown(f"### Step 2: Create snowflake schema in `{env.lower()}.tfvars`")
                schema_block = ""
                for schema in schemas:
                    schema_block += f'"{db_upper}.{schema}" = {{}}\n'
                code_with_copy(schema_block.strip())

                st.markdown(f"### Step 3: Create snowflake_account_roles in `{env.lower()}.tfvars`")
                roles_block = ""
                for schema in schemas:
                    read_role = f"{db_upper}__{schema}__READ_ONLY__ACCESS_ROLE"
                    ddl_role = f"{db_upper}__{schema}__DDL__ACCESS_ROLE"
                    dml_role = f"{db_upper}__{schema}__DML__ACCESS_ROLE"

                    roles_block += f"""{read_role} = {{
  comment          = "For schema {db_upper}.{schema}, grants select on current and future tables and views, grants usage of current and future functions and procedures"
  parent_role_file = "{read_role}.txt"
}}

{ddl_role} = {{
  comment          = "For schema {db_upper}.{schema}, in addition to read accesses, grants create table, iceberg table, view, materialized view, procedure, function, file format, stage, pipe, stream, and task"
  parent_role_file = "{ddl_role}.txt"
}}

{dml_role} = {{
  comment          = "For schema {db_upper}.{schema}, in addition to read accesses, grants insert, update, and delete on tables"
  parent_role_file = "{dml_role}.txt"
}}

"""
                code_with_copy(roles_block.strip())

                st.markdown(f"### Download parent role files ({env})")
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for schema in schemas:
                        read_role = f"{db_upper}__{schema}__READ_ONLY__ACCESS_ROLE"
                        ddl_role = f"{db_upper}__{schema}__DDL__ACCESS_ROLE"
                        dml_role = f"{db_upper}__{schema}__DML__ACCESS_ROLE"
                        zf.writestr(f"{read_role}.txt", "DNA_READ_ONLY_ROLE")
                        ddl_content = ddl_contents.get(env, "")
                        if schema in ["CONFORMED", "STAGING"]:
                            ddl_content += "\n,DBT_SVC_ROLE"
                        zf.writestr(f"{ddl_role}.txt", ddl_content)
                        zf.writestr(f"{dml_role}.txt", "")
                zip_buffer.seek(0)
                st.download_button(
                    label=f"zip_{env.lower()}",
                    data=zip_buffer.getvalue(),
                    file_name=f"{db_upper}_{env.lower()}_parent_roles.zip",
                    mime="application/zip",
                    key=f"zip_{db_upper}_{env}_{rc}",
                )


        elif db_type_val == "Mixer":
            schemas = ["STAGING", "CONFORMED"]
            num_roles = len(schemas) * 3
            num_files = num_roles

            st.markdown("---")
            st.subheader("Preview")
            st.info(f"**Database:** {db_upper}  \n**Schemas:** {', '.join(schemas)}  \n**Roles to create:** {num_roles}  \n**Parent role files:** {num_files}  \n**Environments:** {', '.join(envs_gen)}")

            ddl_contents = {
                "DEV": "OPENLAKEHOUSE_ANALYTICAL_ENGINEER_ROLE\n,CLOUD_COMPOSER_ROLE",
                "QA": "OPENLAKEHOUSE_QA_ENGINEER_ROLE\n,CLOUD_COMPOSER_ROLE",
                "CERT": "OPENLAKEHOUSE_UAT_ENGINEER_ROLE\n,CLOUD_COMPOSER_ROLE",
                "PROD": "OPENLAKEHOUSE_SUPPORT_ENGINEER_ROLE\n,CLOUD_COMPOSER_ROLE",
            }

            for env in envs_gen:
                st.markdown("---")
                st.markdown(f"## Environment: {env}")

                st.markdown(f"### Step 1: Add database under snowflake_database section in `{env.lower()}.tfvars`")
                step1 = f"""{db_upper} = {{
  comment = "Integration database for {db_upper.lower().replace('_', ' ')} data combining multiple sources for downstream applications"
}}"""
                code_with_copy(step1)

                st.markdown(f"### Step 2: Create snowflake schema in `{env.lower()}.tfvars`")
                schema_block = ""
                for schema in schemas:
                    schema_block += f'"{db_upper}.{schema}" = {{}}\n'
                code_with_copy(schema_block.strip())

                st.markdown(f"### Step 3: Create snowflake_account_roles in `{env.lower()}.tfvars`")
                roles_block = ""
                for schema in schemas:
                    read_role = f"{db_upper}__{schema}__READ_ONLY__ACCESS_ROLE"
                    ddl_role = f"{db_upper}__{schema}__DDL__ACCESS_ROLE"
                    dml_role = f"{db_upper}__{schema}__DML__ACCESS_ROLE"

                    roles_block += f"""{read_role} = {{
  comment          = "For schema {db_upper}.{schema}, read-only access."
  parent_role_file = "{read_role}.txt"
}}

{ddl_role} = {{
  comment          = "For schema {db_upper}.{schema}, DDL privileges for analytical engineering."
  parent_role_file = "{ddl_role}.txt"
}}

{dml_role} = {{
  comment          = "For schema {db_upper}.{schema}, DML privileges if required by services."
  parent_role_file = "{dml_role}.txt"
}}

"""
                code_with_copy(roles_block.strip())

                st.markdown(f"### Download parent role files ({env})")
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for schema in schemas:
                        read_role = f"{db_upper}__{schema}__READ_ONLY__ACCESS_ROLE"
                        ddl_role = f"{db_upper}__{schema}__DDL__ACCESS_ROLE"
                        dml_role = f"{db_upper}__{schema}__DML__ACCESS_ROLE"
                        zf.writestr(f"{read_role}.txt", "DNA_READ_ONLY_ROLE")
                        ddl_content = ddl_contents.get(env, "")
                        if schema in ["CONFORMED", "STAGING"]:
                            ddl_content += "\n,DBT_SVC_ROLE"
                        zf.writestr(f"{ddl_role}.txt", ddl_content)
                        zf.writestr(f"{dml_role}.txt", "")
                zip_buffer.seek(0)
                st.download_button(
                    label=f"zip_{env.lower()}",
                    data=zip_buffer.getvalue(),
                    file_name=f"{db_upper}_{env.lower()}_parent_roles.zip",
                    mime="application/zip",
                    key=f"zip_{db_upper}_{env}_{rc}",
                )


        else:
            if not db_upper.endswith("_APP"):
                db_upper = f"{db_upper}_APP"
            schemas = ["STAGING", "CONFORMED", "CONSUMPTION"]
            num_roles = len(schemas) * 3
            num_files = num_roles

            st.markdown("---")
            st.subheader("Preview")
            st.info(f"**Database:** {db_upper}  \n**Schemas:** {', '.join(schemas)}  \n**Roles to create:** {num_roles}  \n**Parent role files:** {num_files}  \n**Environments:** {', '.join(envs_gen)}")

            ddl_contents = {
                "DEV": "OPENLAKEHOUSE_ANALYTICAL_ENGINEER_ROLE\n,CLOUD_COMPOSER_ROLE",
                "QA": "OPENLAKEHOUSE_QA_ENGINEER_ROLE\n,CLOUD_COMPOSER_ROLE",
                "CERT": "OPENLAKEHOUSE_UAT_ENGINEER_ROLE\n,CLOUD_COMPOSER_ROLE",
                "PROD": "OPENLAKEHOUSE_SUPPORT_ENGINEER_ROLE\n,CLOUD_COMPOSER_ROLE",
            }

            for env in envs_gen:
                st.markdown("---")
                st.markdown(f"## Environment: {env}")

                st.markdown(f"### Step 1: Add database under snowflake_database section in `{env.lower()}.tfvars`")
                step1 = f"""{db_upper} = {{
  comment = "Consumption db"
}}"""
                code_with_copy(step1)

                st.markdown(f"### Step 2: Create snowflake schema in `{env.lower()}.tfvars`")
                schema_block = ""
                for schema in schemas:
                    schema_block += f'"{db_upper}.{schema}" = {{}}\n'
                code_with_copy(schema_block.strip())

                st.markdown(f"### Step 3: Create snowflake_account_roles in `{env.lower()}.tfvars`")
                roles_block = ""
                for schema in schemas:
                    read_role = f"{db_upper}__{schema}__READ_ONLY__ACCESS_ROLE"
                    ddl_role = f"{db_upper}__{schema}__DDL__ACCESS_ROLE"
                    dml_role = f"{db_upper}__{schema}__DML__ACCESS_ROLE"

                    roles_block += f"""{read_role} = {{
  comment          = "For schema {db_upper}.{schema}, grants select on current and future tables and views, grants usage of current and future functions and procedures"
  parent_role_file = "{read_role}.txt"
}}

{ddl_role} = {{
  comment          = "For schema {db_upper}.{schema}, in addition to read accesses, grants create table, iceberg table, view, materialized view, procedure, function, file format, stage, pipe, stream, and task"
  parent_role_file = "{ddl_role}.txt"
}}

{dml_role} = {{
  comment          = "For schema {db_upper}.{schema}, in addition to read accesses, grants insert, update, and delete on tables"
  parent_role_file = "{dml_role}.txt"
}}

"""
                code_with_copy(roles_block.strip())

                st.markdown(f"### Step 4: Database privileges in `{env.lower()}.tfvars`")
                step4 = f"""{db_upper} = ["CREATE SCHEMA"]"""
                code_with_copy(step4)

                st.markdown(f"### Step 5: Download parent role files ({env})")
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for schema in schemas:
                        read_role = f"{db_upper}__{schema}__READ_ONLY__ACCESS_ROLE"
                        ddl_role = f"{db_upper}__{schema}__DDL__ACCESS_ROLE"
                        dml_role = f"{db_upper}__{schema}__DML__ACCESS_ROLE"
                        zf.writestr(f"{read_role}.txt", "DNA_READ_ONLY_ROLE")
                        ddl_content = ddl_contents.get(env, "")
                        if schema in ["CONFORMED", "STAGING"]:
                            ddl_content += "\n,DBT_SVC_ROLE"
                        zf.writestr(f"{ddl_role}.txt", ddl_content)
                        zf.writestr(f"{dml_role}.txt", "")
                zip_buffer.seek(0)
                st.download_button(
                    label=f"zip_{env.lower()}",
                    data=zip_buffer.getvalue(),
                    file_name=f"{db_upper}_{env.lower()}_parent_roles.zip",
                    mime="application/zip",
                    key=f"zip_{db_upper}_{env}_{rc}",
                )

