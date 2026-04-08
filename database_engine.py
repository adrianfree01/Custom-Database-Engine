import re
import ast
import random


class DatabaseError(Exception):
    pass


class TableAlreadyExistsError(DatabaseError):
    pass


class TableNotFoundError(DatabaseError):
    pass


class SchemaError(DatabaseError):
    pass


class RowValidationError(DatabaseError):
    pass


class ConstraintError(DatabaseError):
    pass


class ForeignKeyError(DatabaseError):
    pass


class Schema:
    def __init__(self, columns, primary_key=None, foreign_keys=None):
        if not columns:
            raise SchemaError("Schema must contain at least one column.")

        self.columns = columns
        self.primary_key = primary_key
        self.foreign_keys = foreign_keys if foreign_keys is not None else {}

        if self.primary_key is not None and self.primary_key not in self.columns:
            raise SchemaError(f"Primary key column '{self.primary_key}' does not exist.")

        for column_name, fk_info in self.foreign_keys.items():
            if column_name not in self.columns:
                raise SchemaError(f"Foreign key column '{column_name}' does not exist.")

            if "table" not in fk_info or "column" not in fk_info:
                raise SchemaError(
                    f"Foreign key for '{column_name}' must include table and column."
                )

    def get_column_names(self):
        return list(self.columns.keys())

    def validate_row_shape(self, data):
        if len(data) != len(self.columns):
            raise SchemaError(
                f"Expected {len(self.columns)} values, got {len(data)}."
            )

    def validate_row_types(self, data):
        self.validate_row_shape(data)

        for (column_name, expected_type), value in zip(self.columns.items(), data):
            if not isinstance(value, expected_type):
                raise RowValidationError(
                    f"Column '{column_name}' expected {expected_type.__name__}, "
                    f"got {type(value).__name__}."
                )


class Row:
    def __init__(self, data, schema):
        self.schema = schema
        self.schema.validate_row_types(data)

        self.data = {
            column_name: value
            for column_name, value in zip(self.schema.get_column_names(), data)
        }

    def get(self, column_name):
        return self.data[column_name]

    def set(self, column_name, value):
        self.data[column_name] = value

    def to_dict(self):
        return dict(self.data)


class Table:
    def __init__(self, name, schema):
        self.name = name
        self.schema = schema
        self.rows = []

    def has_value_in_column(self, column_name, value):
        for row in self.rows:
            if row.get(column_name) == value:
                return True
        return False

    def find_rows(self, column_name, value):
        return [row for row in self.rows if row.get(column_name) == value]

    def insert_row(self, data):
        row = Row(data, self.schema)
        self.rows.append(row)
        return row

    def select_all(self):
        return [row.to_dict() for row in self.rows]

    def find_by_column(self, column_name, value):
        return [row.to_dict() for row in self.rows if row.get(column_name) == value]

    def delete_by_column(self, column_name, value):
        original_count = len(self.rows)
        self.rows = [row for row in self.rows if row.get(column_name) != value]
        return original_count - len(self.rows)

    def update_by_column(self, search_column, search_value, update_column, new_value):
        updated_count = 0

        if update_column not in self.schema.columns:
            raise SchemaError(f"Column '{update_column}' does not exist.")

        expected_type = self.schema.columns[update_column]
        if not isinstance(new_value, expected_type):
            raise RowValidationError(
                f"Column '{update_column}' expected {expected_type.__name__}, "
                f"got {type(new_value).__name__}."
            )

        for row in self.rows:
            if row.get(search_column) == search_value:
                row.set(update_column, new_value)
                updated_count += 1

        return updated_count

    def row_count(self):
        return len(self.rows)


class Database:
    def __init__(self, database_id, name):
        self.id = database_id
        self.name = name
        self.tables = {}

        self.query_count = 0
        self.insert_count = 0
        self.update_count = 0
        self.delete_count = 0

    def create_table(self, name, columns, primary_key=None, foreign_keys=None):
        if name in self.tables:
            raise TableAlreadyExistsError(f"Table '{name}' already exists.")

        schema = Schema(columns, primary_key, foreign_keys)
        self.tables[name] = Table(name, schema)
        return self.tables[name]

    def drop_table(self, name):
        if name not in self.tables:
            raise TableNotFoundError(f"Table '{name}' does not exist.")

        for other_table in self.tables.values():
            for fk_column, fk_info in other_table.schema.foreign_keys.items():
                if fk_info["table"] == name:
                    raise ConstraintError(
                        f"Cannot drop table '{name}' because it is referenced by "
                        f"foreign key '{fk_column}' in table '{other_table.name}'."
                    )

        del self.tables[name]

    def get_table(self, name):
        if name not in self.tables:
            raise TableNotFoundError(f"Table '{name}' does not exist.")
        return self.tables[name]

    def list_tables(self):
        return list(self.tables.keys())

    def _validate_primary_key_on_insert(self, table, row_data):
        pk = table.schema.primary_key
        if pk is None:
            return

        pk_value = row_data[pk]
        if table.has_value_in_column(pk, pk_value):
            raise ConstraintError(
                f"Duplicate primary key value '{pk_value}' for column '{pk}'."
            )

    def _validate_foreign_keys_on_insert(self, table, row_data):
        for fk_column, fk_info in table.schema.foreign_keys.items():
            fk_value = row_data[fk_column]
            referenced_table = self.get_table(fk_info["table"])
            referenced_column = fk_info["column"]

            if not referenced_table.has_value_in_column(referenced_column, fk_value):
                raise ForeignKeyError(
                    f"Foreign key constraint failed on '{fk_column}': "
                    f"value '{fk_value}' not found in "
                    f"{fk_info['table']}.{referenced_column}."
                )

    def _validate_delete_against_foreign_keys(self, table_name, column_name, value):
        for other_table in self.tables.values():
            for fk_column, fk_info in other_table.schema.foreign_keys.items():
                if fk_info["table"] == table_name and fk_info["column"] == column_name:
                    if other_table.has_value_in_column(fk_column, value):
                        raise ForeignKeyError(
                            f"Cannot delete value '{value}' from {table_name}.{column_name} "
                            f"because it is referenced by {other_table.name}.{fk_column}."
                        )

    def insert_into(self, table_name, data):
        table = self.get_table(table_name)
        row = Row(data, table.schema)

        self._validate_primary_key_on_insert(table, row.data)
        self._validate_foreign_keys_on_insert(table, row.data)

        table.rows.append(row)
        self.insert_count += 1
        return row

    def select_all_from(self, table_name):
        self.query_count += 1
        return self.get_table(table_name).select_all()

    def find_in_table(self, table_name, column_name, value):
        self.query_count += 1
        return self.get_table(table_name).find_by_column(column_name, value)

    def delete_from_table(self, table_name, column_name, value):
        table = self.get_table(table_name)

        rows_to_delete = table.find_rows(column_name, value)
        for row in rows_to_delete:
            pk = table.schema.primary_key
            if pk is not None:
                self._validate_delete_against_foreign_keys(table_name, pk, row.get(pk))
            else:
                self._validate_delete_against_foreign_keys(table_name, column_name, value)

        deleted = table.delete_by_column(column_name, value)
        self.delete_count += deleted
        return deleted

    def update_in_table(self, table_name, search_column, search_value, update_column, new_value):
        table = self.get_table(table_name)

        if update_column == table.schema.primary_key:
            for row in table.rows:
                if row.get(search_column) != search_value and row.get(update_column) == new_value:
                    raise ConstraintError(
                        f"Duplicate primary key value '{new_value}' for column '{update_column}'."
                    )

        if update_column in table.schema.foreign_keys:
            fk_info = table.schema.foreign_keys[update_column]
            referenced_table = self.get_table(fk_info["table"])
            referenced_column = fk_info["column"]

            if not referenced_table.has_value_in_column(referenced_column, new_value):
                raise ForeignKeyError(
                    f"Foreign key constraint failed on '{update_column}': "
                    f"value '{new_value}' not found in "
                    f"{fk_info['table']}.{referenced_column}."
                )

        updated = table.update_by_column(search_column, search_value, update_column, new_value)
        self.update_count += updated
        return updated

    def get_stats(self):
        total_rows = sum(table.row_count() for table in self.tables.values())
        return {
            "databaseId": self.id,
            "databaseName": self.name,
            "tableCount": len(self.tables),
            "totalRows": total_rows,
            "queryCount": self.query_count,
            "insertCount": self.insert_count,
            "updateCount": self.update_count,
            "deleteCount": self.delete_count
        }

    def _parse_type(self, type_name):
        type_map = {
            "int": int,
            "str": str,
            "float": float,
            "bool": bool
        }

        if type_name not in type_map:
            raise ValueError(f"Unsupported type: {type_name}")

        return type_map[type_name]

    def _parse_value(self, raw_value):
        raw_value = raw_value.strip()

        if raw_value.startswith('"') and raw_value.endswith('"'):
            return raw_value[1:-1]

        if raw_value.startswith("'") and raw_value.endswith("'"):
            return raw_value[1:-1]

        if raw_value.lower() == "true":
            return True

        if raw_value.lower() == "false":
            return False

        if "." in raw_value:
            try:
                return float(raw_value)
            except ValueError:
                pass

        try:
            return int(raw_value)
        except ValueError:
            pass

        return raw_value

    def _type_name(self, value_type):
        reverse_map = {
            int: "int",
            str: "str",
            float: "float",
            bool: "bool"
        }
        return reverse_map.get(value_type, value_type.__name__)

    def describe_table(self, table_name):
        table = self.get_table(table_name)
        schema = table.schema
        columns = []

        for column_name, column_type in schema.columns.items():
            fk_info = schema.foreign_keys.get(column_name)
            columns.append({
                "name": column_name,
                "type": self._type_name(column_type),
                "isPrimaryKey": column_name == schema.primary_key,
                "foreignKey": fk_info
            })

        return {
            "tableName": table_name,
            "rowCount": table.row_count(),
            "columns": columns
        }

    def _split_csv(self, text):
        parts = []
        current = ""
        in_quotes = False
        quote_char = ""

        for char in text:
            if char in ['"', "'"]:
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif quote_char == char:
                    in_quotes = False
                current += char
            elif char == "," and not in_quotes:
                parts.append(current.strip())
                current = ""
            else:
                current += char

        if current.strip():
            parts.append(current.strip())

        return parts

    def _split_statements(self, text):
        statements = []
        current = ""
        in_quotes = False
        quote_char = ""

        for char in text:
            if char in ['"', "'"]:
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif quote_char == char:
                    in_quotes = False
                current += char
            elif char == ";" and not in_quotes:
                if current.strip():
                    statements.append(current.strip())
                current = ""
            else:
                current += char

        if current.strip():
            statements.append(current.strip())

        return statements

    def _safe_eval_math(self, expression, variables):
        node = ast.parse(expression, mode="eval")

        def _eval(current):
            if isinstance(current, ast.Expression):
                return _eval(current.body)
            if isinstance(current, ast.Constant):
                if isinstance(current.value, (int, float)):
                    return current.value
                raise ValueError("Only numeric constants are allowed in ID_EXPR.")
            if isinstance(current, ast.Name):
                if current.id in variables:
                    return variables[current.id]
                raise ValueError(f"Unknown variable '{current.id}' in ID_EXPR.")
            if isinstance(current, ast.BinOp):
                left = _eval(current.left)
                right = _eval(current.right)

                if isinstance(current.op, ast.Add):
                    return left + right
                if isinstance(current.op, ast.Sub):
                    return left - right
                if isinstance(current.op, ast.Mult):
                    return left * right
                if isinstance(current.op, ast.Div):
                    return left / right
                if isinstance(current.op, ast.FloorDiv):
                    return left // right
                if isinstance(current.op, ast.Mod):
                    return left % right
                if isinstance(current.op, ast.Pow):
                    return left ** right

                raise ValueError("Unsupported operator in ID_EXPR.")
            if isinstance(current, ast.UnaryOp):
                operand = _eval(current.operand)
                if isinstance(current.op, ast.UAdd):
                    return +operand
                if isinstance(current.op, ast.USub):
                    return -operand
                raise ValueError("Unsupported unary operator in ID_EXPR.")

            raise ValueError("Unsupported expression in ID_EXPR.")

        return _eval(node)

    def _parse_string_list(self, text):
        values = [self._parse_value(item) for item in self._split_csv(text)]
        if not values:
            raise ValueError("List cannot be empty.")
        for value in values:
            if not isinstance(value, str):
                raise ValueError("Name lists must contain only strings.")
        return values

    def _insert_name_grid(
        self,
        table_name,
        id_column,
        first_column,
        last_column,
        first_names,
        last_names,
        start_id=1,
        id_expr=None
    ):
        table = self.get_table(table_name)
        schema_columns = set(table.schema.get_column_names())
        required_columns = {id_column, first_column, last_column}

        missing = required_columns - schema_columns
        if missing:
            raise SchemaError(f"Missing required column(s) in table '{table_name}': {sorted(missing)}")

        extra = schema_columns - required_columns
        if extra:
            raise SchemaError(
                f"Table '{table_name}' has extra column(s) not supplied by name grid: {sorted(extra)}. "
                "Use a table with exactly these three columns or insert rows manually."
            )

        inserted_rows = []
        row_index = 0

        for i, first_name in enumerate(first_names):
            for j, last_name in enumerate(last_names):
                variables = {
                    "i": i,
                    "j": j,
                    "i1": i + 1,
                    "j1": j + 1,
                    "row_index": row_index,
                    "row_number": row_index + 1,
                    "start_id": start_id,
                    "first_count": len(first_names),
                    "last_count": len(last_names)
                }

                if id_expr is None:
                    generated_id = start_id + row_index
                else:
                    generated_id = self._safe_eval_math(id_expr, variables)

                row_data_by_column = {
                    id_column: generated_id,
                    first_column: first_name,
                    last_column: last_name
                }
                ordered_row = [row_data_by_column[col] for col in table.schema.get_column_names()]
                row = self.insert_into(table_name, ordered_row)
                inserted_rows.append(row.to_dict())
                row_index += 1

        return inserted_rows

    def _insert_random_users(self, table_name, count, start_id=1, age_min=18, age_max=90):
        if count <= 0:
            raise ValueError("COUNT must be greater than zero.")
        if age_min > age_max:
            raise ValueError("AGE_RANGE minimum cannot be greater than maximum.")

        first_names = [
            "Ava", "Liam", "Noah", "Emma", "Mia", "Olivia", "Ethan", "Lucas",
            "Ivy", "Aria", "Mason", "Sophia", "Leo", "Chloe", "Elijah", "Nora",
            "Ezra", "Mila", "Owen", "Zoe"
        ]
        last_names = [
            "Smith", "Johnson", "Brown", "Taylor", "Miller", "Wilson", "Moore",
            "Clark", "Hall", "Young", "Allen", "King", "Wright", "Scott",
            "Green", "Baker", "Adams", "Nelson", "Hill", "Campbell"
        ]

        table = self.get_table(table_name)
        schema_columns = set(table.schema.get_column_names())
        required_columns = {"id", "fname", "lname", "age"}

        missing = required_columns - schema_columns
        if missing:
            raise SchemaError(
                f"Missing required column(s) in table '{table_name}': {sorted(missing)}"
            )

        extra = schema_columns - required_columns
        if extra:
            raise SchemaError(
                f"Table '{table_name}' has extra column(s) not supplied by random user generator: {sorted(extra)}."
            )

        preview_rows = []
        for row_index in range(count):
            row_data_by_column = {
                "id": start_id + row_index,
                "fname": random.choice(first_names),
                "lname": random.choice(last_names),
                "age": random.randint(age_min, age_max)
            }
            ordered_row = [row_data_by_column[col] for col in table.schema.get_column_names()]
            row = self.insert_into(table_name, ordered_row)

            if row_index < 10:
                preview_rows.append(row.to_dict())

        return {
            "generatedCount": count,
            "previewRows": preview_rows
        }

    def run_query(self, query):
        query = query.strip()
        if query.endswith(";"):
            query = query[:-1].strip()

        create_match = re.match(
            r"CREATE TABLE (\w+)\s*\((.+)\)$",
            query,
            re.IGNORECASE
        )
        if create_match:
            table_name = create_match.group(1)
            columns_text = create_match.group(2)

            columns = {}
            primary_key = None
            foreign_keys = {}

            for item in self._split_csv(columns_text):
                item = item.strip()

                fk_match = re.match(
                    r"FOREIGN KEY\s*\((\w+)\)\s+REFERENCES\s+(\w+)\s*\((\w+)\)",
                    item,
                    re.IGNORECASE
                )
                if fk_match:
                    local_column = fk_match.group(1)
                    referenced_table = fk_match.group(2)
                    referenced_column = fk_match.group(3)

                    foreign_keys[local_column] = {
                        "table": referenced_table,
                        "column": referenced_column
                    }
                    continue

                parts = item.split()
                if len(parts) < 2:
                    raise ValueError(f"Invalid column definition: {item}")

                column_name = parts[0]
                type_name = parts[1].lower()

                columns[column_name] = self._parse_type(type_name)

                if len(parts) >= 3:
                    constraint_text = " ".join(parts[2:]).upper()
                    if constraint_text == "PRIMARY KEY":
                        if primary_key is not None:
                            raise ConstraintError("Only one primary key is supported.")
                        primary_key = column_name

            self.create_table(table_name, columns, primary_key, foreign_keys)

            return {
                "ok": True,
                "message": f"Table '{table_name}' created.",
                "primaryKey": primary_key,
                "foreignKeys": foreign_keys
            }

        drop_match = re.match(
            r"DROP TABLE (\w+)$",
            query,
            re.IGNORECASE
        )
        if drop_match:
            table_name = drop_match.group(1)
            self.drop_table(table_name)
            return {
                "ok": True,
                "message": f"Table '{table_name}' dropped."
            }

        drop_if_exists_all_match = re.match(
            r"DROP TABLE IF EXISTS \*$",
            query,
            re.IGNORECASE
        )
        if drop_if_exists_all_match:
            dropped_count = len(self.tables)
            self.tables = {}
            return {
                "ok": True,
                "message": f"Dropped {dropped_count} table(s).",
                "droppedCount": dropped_count
            }

        drop_if_exists_match = re.match(
            r"DROP TABLE IF EXISTS (\w+)$",
            query,
            re.IGNORECASE
        )
        if drop_if_exists_match:
            table_name = drop_if_exists_match.group(1)
            if table_name in self.tables:
                self.drop_table(table_name)
                return {
                    "ok": True,
                    "message": f"Table '{table_name}' dropped."
                }
            return {
                "ok": True,
                "message": f"Table '{table_name}' did not exist."
            }

        insert_match = re.match(
            r"INSERT INTO (\w+)\s+VALUES\s*\((.+)\)$",
            query,
            re.IGNORECASE
        )
        if insert_match:
            table_name = insert_match.group(1)
            values_text = insert_match.group(2)
            values = [self._parse_value(v) for v in self._split_csv(values_text)]
            row = self.insert_into(table_name, values)

            return {
                "ok": True,
                "message": "Row inserted.",
                "row": row.to_dict()
            }

        insert_grid_match = re.match(
            r"INSERT GRID INTO (\w+)\s*\((\w+)\s*,\s*(\w+)\s*,\s*(\w+)\)\s+"
            r"FIRSTNAMES\s*\((.+?)\)\s+LASTNAMES\s*\((.+?)\)"
            r"(?:\s+START_ID\s+(-?\d+))?"
            r"(?:\s+ID_EXPR\s*\((.+)\))?$",
            query,
            re.IGNORECASE
        )
        if insert_grid_match:
            table_name = insert_grid_match.group(1)
            id_column = insert_grid_match.group(2)
            first_column = insert_grid_match.group(3)
            last_column = insert_grid_match.group(4)
            first_names_text = insert_grid_match.group(5)
            last_names_text = insert_grid_match.group(6)
            start_id_text = insert_grid_match.group(7)
            id_expr = insert_grid_match.group(8)

            first_names = self._parse_string_list(first_names_text)
            last_names = self._parse_string_list(last_names_text)
            start_id = int(start_id_text) if start_id_text is not None else 1

            inserted_rows = self._insert_name_grid(
                table_name=table_name,
                id_column=id_column,
                first_column=first_column,
                last_column=last_column,
                first_names=first_names,
                last_names=last_names,
                start_id=start_id,
                id_expr=id_expr
            )

            return {
                "ok": True,
                "message": f"Inserted {len(inserted_rows)} generated row(s).",
                "generatedCount": len(inserted_rows),
                "rows": inserted_rows
            }

        insert_random_users_match = re.match(
            r"INSERT RANDOM USERS INTO (\w+)\s+COUNT\s+(\d+)"
            r"(?:\s+START_ID\s+(-?\d+))?"
            r"(?:\s+AGE_RANGE\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\))?$",
            query,
            re.IGNORECASE
        )
        if insert_random_users_match:
            table_name = insert_random_users_match.group(1)
            count = int(insert_random_users_match.group(2))
            start_id_text = insert_random_users_match.group(3)
            age_min_text = insert_random_users_match.group(4)
            age_max_text = insert_random_users_match.group(5)

            start_id = int(start_id_text) if start_id_text is not None else 1
            age_min = int(age_min_text) if age_min_text is not None else 18
            age_max = int(age_max_text) if age_max_text is not None else 90

            generated = self._insert_random_users(
                table_name=table_name,
                count=count,
                start_id=start_id,
                age_min=age_min,
                age_max=age_max
            )

            return {
                "ok": True,
                "message": f"Inserted {generated['generatedCount']} random user row(s).",
                "generatedCount": generated["generatedCount"],
                "previewRows": generated["previewRows"]
            }

        select_where_match = re.match(
            r"SELECT \* FROM (\w+)\s+WHERE\s+(\w+)\s*=\s*(.+)$",
            query,
            re.IGNORECASE
        )
        if select_where_match:
            table_name = select_where_match.group(1)
            column_name = select_where_match.group(2)
            value = self._parse_value(select_where_match.group(3))
            rows = self.find_in_table(table_name, column_name, value)

            return {
                "ok": True,
                "rows": rows
            }

        select_all_match = re.match(
            r"SELECT \* FROM (\w+)$",
            query,
            re.IGNORECASE
        )
        if select_all_match:
            table_name = select_all_match.group(1)
            rows = self.select_all_from(table_name)

            return {
                "ok": True,
                "rows": rows
            }

        select_count_match = re.match(
            r"SELECT COUNT\(\*\) FROM (\w+)$",
            query,
            re.IGNORECASE
        )
        if select_count_match:
            table_name = select_count_match.group(1)
            count = self.get_table(table_name).row_count()
            self.query_count += 1
            return {
                "ok": True,
                "count": count
            }

        update_match = re.match(
            r"UPDATE (\w+)\s+SET\s+(\w+)\s*=\s*(.+?)\s+WHERE\s+(\w+)\s*=\s*(.+)$",
            query,
            re.IGNORECASE
        )
        if update_match:
            table_name = update_match.group(1)
            update_column = update_match.group(2)
            new_value = self._parse_value(update_match.group(3))
            search_column = update_match.group(4)
            search_value = self._parse_value(update_match.group(5))

            updated = self.update_in_table(
                table_name,
                search_column,
                search_value,
                update_column,
                new_value
            )

            return {
                "ok": True,
                "message": f"Updated {updated} row(s)."
            }

        delete_match = re.match(
            r"DELETE FROM (\w+)\s+WHERE\s+(\w+)\s*=\s*(.+)$",
            query,
            re.IGNORECASE
        )
        if delete_match:
            table_name = delete_match.group(1)
            column_name = delete_match.group(2)
            value = self._parse_value(delete_match.group(3))
            deleted = self.delete_from_table(table_name, column_name, value)

            return {
                "ok": True,
                "message": f"Deleted {deleted} row(s)."
            }

        if query.upper() == "SHOW TABLES":
            return {
                "ok": True,
                "tables": self.list_tables()
            }

        show_from_match = re.match(
            r"SHOW \* FROM (\w+)$",
            query,
            re.IGNORECASE
        )
        if show_from_match:
            table_name = show_from_match.group(1)
            rows = self.select_all_from(table_name)
            return {
                "ok": True,
                "rows": rows
            }

        show_all_match = re.match(
            r"SHOW \* FROM \*$",
            query,
            re.IGNORECASE
        )
        if show_all_match:
            self.query_count += 1
            tables = {}

            for table_name in self.list_tables():
                tables[table_name] = self.get_table(table_name).select_all()

            return {
                "ok": True,
                "tables": tables
            }

        describe_match = re.match(
            r"DESCRIBE (\w+)$",
            query,
            re.IGNORECASE
        )
        if describe_match:
            self.query_count += 1
            table_name = describe_match.group(1)
            return {
                "ok": True,
                "schema": self.describe_table(table_name)
            }

        if query.upper() == "SHOW STATS":
            return {
                "ok": True,
                "stats": self.get_stats()
            }

        raise ValueError("Unsupported query.")

    def run_bulk_queries(self, text):
        statements = self._split_statements(text)
        results = []

        for index, statement in enumerate(statements, start=1):
            try:
                result = self.run_query(statement)
                results.append({
                    "statementNumber": index,
                    "statement": statement,
                    "result": result
                })
            except Exception as exc:
                results.append({
                    "statementNumber": index,
                    "statement": statement,
                    "result": {
                        "ok": False,
                        "error": str(exc)
                    }
                })

        return {
            "ok": True,
            "statementCount": len(statements),
            "results": results
        }
