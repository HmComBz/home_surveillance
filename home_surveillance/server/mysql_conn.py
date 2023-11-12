import mysql.connector
import logging
import os

# Set logger for mysql
logger = logging.getLogger('mysql.connector')
logger.setLevel(logging.ERROR)

# Get environmental variables
user = os.getenv('MYSQL_USER')
password = os.getenv('MYSQL_PASS')
host = os.getenv('MYSQL_HOST')
db = os.getenv('MYSQL_DB_HS')


class MysqlConnection():
    def __init__(self):
        pass

    #---------------------------------------------------------------------------
    def create_connection(self):
        ''' Create cursor object '''

        # Create connection object
        cnx = mysql.connector.connect(user=user, password=password,
                                      host=host,
                                      database=db)
        return cnx
    
    #---------------------------------------------------------------------------
    def custom_query_data(self, query):
        ''' Query data from database '''
  
        # Create cursor object
        cnx = self.create_connection()
        cursor = cnx.cursor()

        # Execute
        cursor.execute(query)

        # Get results
        results = []
        for row in cursor:
            results.append(row)

        # Close connection
        cnx.commit()
        cursor.close()
        cnx.close()

        return results

    #---------------------------------------------------------------------------
    def example_strings(self):
        ''' Example strings '''

        columns = ["user_id", "alarm_status", "camera_name"]
        table = "app_cameras"
        where_statements = [("id", self.camera_id)]
        cam_obj = MysqlConnection().query_data(columns, table, where_statements)[0]

    #---------------------------------------------------------------------------
    def query_data(self, columns, table, where_statements):
        '''
        Query data from database
            columns = List with column names as strings
            table = String with table name
            where_statements = List of tuples with column name and values
        '''

        # Create cursor object
        cnx = self.create_connection()
        cursor = cnx.cursor()

        # Create start string
        query = "SELECT "

        # Add columns to export
        if columns[0] != "*":
            for c in range(0, len(columns)):
                if c < (len(columns) - 1):
                    query += columns[c] + ", "
                else:
                    query += columns[c] + " FROM "
        else:
            query += "* FROM "

        # Adding where statements
        if len(where_statements) != 0:
            first = False
            for w in where_statements:
                if first != True:
                    query += ("%s WHERE %s = %s" % (table, w[0], w[1]))
                    first = True
                else:
                    query += (" AND %s = %s" % (w[0], w[1]))
        else:
            query += "%s" % table

        # Add final
        query += ";"

        # Execute
        cursor.execute(query)

        # Get results
        results = []
        for row in cursor:
            temp_row = {}
            counter = 0
            for c in columns:
                temp_row[c] = row[counter]
                counter += 1
            results.append(temp_row)

        # Close connection
        cnx.commit()
        cursor.close()
        cnx.close()

        return results

    #---------------------------------------------------------------------------
    def insert_data(self, table, data):
        '''
        Insert data to database
            table = String with table name
            data = List with tuples with column name and values
        '''

        # Create cursor object
        cnx = self.create_connection()
        cursor = cnx.cursor()

        # Create start string
        query = "INSERT INTO %s (" % table

        # Add columns
        data_tuple = []
        first = False
        for d in data:
            if first != True:
                query += ("%s" % d[0])
                data_tuple.append(d[1])
                first = True
            else:
                query += (", %s" % d[0])
                data_tuple.append(d[1])

        # Add values
        query += ") VALUES ("
        first = False
        for d in data:
            if first != True:
                query += "%s"
                first = True
            else:
                query += ", %s"

        # Final string
        query += ")"

        # Execute
        cursor.execute(query, data_tuple)

        # Getting last inserted row id
        query = "SELECT LAST_INSERT_ID();"
        cursor.execute(query)
        row_id = None
        for row in cursor:
            row_id = row[0]

        # Close connection
        cnx.commit()
        cursor.close()
        cnx.close()

        return row_id

    #---------------------------------------------------------------------------
    def update_data(self, table, data, where_statements):
        '''
        Update data in database
            table = String with table name
            data = List with tuples with column name and values
            where_statements = List of tuples with column name and values
        '''

        # Create cursor object
        cnx = self.create_connection()
        cursor = cnx.cursor()

        # Create update string
        query = "UPDATE %s SET" % table

        # Ad data to update
        data_tuple = []
        first = False
        for d in data:
            if first != True:
                query += (" %s" % d[0]) + "=%s"
                data_tuple.append(d[1])
                first = True
            else:
                query += (", %s" % d[0]) + "=%s"
                data_tuple.append(d[1])

        # Ad where statements
        if len(where_statements) != 0:
            first = False
            for w in where_statements:
                if first != True:
                    query += " WHERE %s" % w[0] + "=%s"
                    data_tuple.append(w[1])
                    first = True
                else:
                    query += " AND %s" % w[0] + "=%s"
                    data_tuple.append(w[1])

        # Add final
        query += ";"

        # Execute
        cursor.execute(query, data_tuple)

        # Close connection
        cnx.commit()
        cursor.close()
        cnx.close()

    #---------------------------------------------------------------------------
    def delete_data(self, table, where_statements):
        '''
        Insert data to database
            table = String with table name
            data = List with tuples with column name and values
        '''

        # Create cursor object
        cnx = self.create_connection()
        cursor = cnx.cursor()

        # Create start string
        query = "DELETE FROM %s" % table

        # Ad where statements
        data_tuple = []
        if len(where_statements) != 0:
            first = False
            for w in where_statements:
                if first != True:
                    query += " WHERE %s" % w[0] + "=%s"
                    data_tuple.append(w[1])
                    first = True
                else:
                    query += " AND %s" % w[0] + "=%s"
                    data_tuple.append(w[1])

        # Execute
        cursor.execute(query, data_tuple)

        # Close connection
        cnx.commit()
        cursor.close()
        cnx.close()

    #---------------------------------------------------------------------------
    def count_data(self, table, id_column, group_column, id_value):
        '''
        Group by column
        '''

        # Create cursor object
        cnx = self.create_connection()
        cursor = cnx.cursor()

        # Create start string
        query = "SELECT COUNT(%s) FROM %s WHERE %s=%s GROUP BY %s" % (group_column, table, id_column, id_value, id_column)

        # Execute
        cursor.execute(query)

        # Get results
        results = 0
        for row in cursor:
            results = row[0]

        # Close connection
        cnx.commit()
        cursor.close()
        cnx.close()

        return results
