class database:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.tables = []


    def createTable(self, name, columns):
        newSchema = schema(columns)
        newTable = table(name, newSchema)
        self.tables.append(newTable)

    



class schema:
    def __init__(self, columns):
        self.columns = columns

class table:
    def __init__(self, name, schema):
        self.name = name
        self.schema = schema
        self.rows = []

    def insertRow(self, data):
        newRow = row(data, self.schema)
        self.rows.append(newRow)

class row:
    def __init__(self, data, schema):
        self.schema = schema
        if (len(data) == len(self.schema.columns)):
            for i in range(len(data)):
                if (isinstance(data[i], list(self.schema.columns.values())[i])):
                    continue
                else:
                    raise TypeError(f"Incorrect Data Type for index {i}")
            self.data = data
        else:
            raise ValueError("Incorrect amount of arguments")
