def run_kcm_export():
    import mysql.connector
    import json
    import yaml

    # Path to the docker-compose.yml file
    docker_compose_file = '/etc/kcm-setup/docker-compose.yml'

    # Function to extract database credentials from docker-compose.yml
    def get_db_config_from_compose():
        with open(docker_compose_file, 'r') as file:
            # Load the docker-compose YAML file
            compose_data = yaml.safe_load(file)
            
            # Extracting the necessary information from the 'db' service
            db_service = compose_data['services']['db']
            environment = db_service['environment']
            
            db_name = environment.get('GUACAMOLE_DATABASE', 'guacamole_db')
            db_user = environment.get('GUACAMOLE_USERNAME', 'guacamole_user')
            db_password = environment.get('GUACAMOLE_PASSWORD', 'password')  # Default in case it's not present
            
            return {
                'host': 'localhost',  # Assuming the database is local since it's inside Docker
                'user': db_user,
                'password': db_password,
                'database': db_name,
                'port': 3306  # Default MySQL port
                #'ssl_disabled': True # For self-signed staging hosts
            }

    def build_connection_group_paths(cursor):
        """
        Build a dictionary mapping group IDs to their full paths by resolving parent-child relationships.
        """
        cursor.execute("SELECT connection_group_id, parent_id, connection_group_name FROM guacamole_connection_group")
        groups = cursor.fetchall()

        group_paths = {}

        def resolve_path(group_id):
            if group_id is None:
                return "ROOT"
            if group_id in group_paths:
                return group_paths[group_id]
            # Find the group details
            group = next(g for g in groups if g['connection_group_id'] == group_id)
            parent_path = resolve_path(group['parent_id'])
            full_path = f"{parent_path}/{group['connection_group_name']}"
            group_paths[group_id] = full_path
            return full_path

        # Resolve paths for all groups
        for group in groups:
            resolve_path(group['connection_group_id'])

        return group_paths

    # SQL query to retrieve all connections, users, groups, and attributes
    query = """
    SELECT
        c.connection_id,
        c.connection_name AS name,
        c.protocol,
        cp.parameter_name,
        cp.parameter_value,
        e.name AS entity_name,
        e.type AS entity_type,
        g.connection_group_id,
        g.parent_id,
        g.connection_group_name AS group_name,
        ca.attribute_name,
        ca.attribute_value
    FROM
        guacamole_connection c
    LEFT JOIN
        guacamole_connection_parameter cp ON c.connection_id = cp.connection_id
    LEFT JOIN
        guacamole_connection_attribute ca ON c.connection_id = ca.connection_id
    LEFT JOIN
        guacamole_connection_group g ON c.parent_id = g.connection_group_id
    LEFT JOIN
        guacamole_connection_permission p ON c.connection_id = p.connection_id
    LEFT JOIN
        guacamole_entity e ON p.entity_id = e.entity_id;
    """

    def export_to_json(db_config):
        try:
            # Connect to the database
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor(dictionary=True)  # Dictionary cursor for better handling

            # Build connection group paths
            connection_group_paths = build_connection_group_paths(cursor) 

            # Execute the query
            cursor.execute(query)
            rows = cursor.fetchall()

            # Organize the data into the expected format
            connections = {}
            for row in rows:
                conn_id = row['connection_id']
                if conn_id not in connections:
                    # Resolve connection group path
                    group_path = connection_group_paths.get(row['connection_group_id'], "ROOT")
                    connections[conn_id] = {
                        'name': row['name'],
                        'protocol': row['protocol'],
                        'parameters': {},
                        'users': [],
                        'groups': [],  # User groups go here
                        'group': group_path,  # Connection group path 
                        'attributes': {}
                    }
                # Handle parameters
                if row['parameter_name']:
                    connections[conn_id]['parameters'][row['parameter_name']] = row['parameter_value']
                # Handle users
                if row['entity_type'] == 'USER' and row['entity_name'] not in connections[conn_id]['users']:
                    connections[conn_id]['users'].append(row['entity_name'])
                # Handle user groups
                if row['entity_type'] == 'USER_GROUP' and row['entity_name'] not in connections[conn_id]['groups']:
                    connections[conn_id]['groups'].append(row['entity_name'])
                # Handle attributes
                if row['attribute_name']:
                    connections[conn_id]['attributes'][row['attribute_name']] = row['attribute_value']

            # Convert to list format
            connection_list = [conn for conn in connections.values()]

            # Output the data to a JSON file
            return connection_list

        except mysql.connector.Error as err:
            print(f"Error: {err}")
        finally:
            # Close the cursor and the connection
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    # Get the database configuration from docker-compose.yml
    db_config = get_db_config_from_compose()
    export_to_json(db_config)

def unpack_export(data):
    result = {}
    # Unpack groups (=>shared folders)
    for obj in data:
        obj['group'] = obj['group'].replace('/','//')
        if obj['group'] not in result:
            result[obj['group']] = {}
        if obj['protocol'] == 'http':
            result[obj['group']][obj['name']]={
                'url': obj['parameters']['url'],
                'autofill': obj['parameters']['autofill-configuration'],
                'protocol':obj['protocol'],
                'username':obj['parameters']['username'],
                'password':obj['parameters']['password']
            }
        else:
            result[obj['group']][obj['name']]={
                'hostname': obj['parameters']['hostname'],
                'port': obj['parameters']['port'],
                'protocol':obj['protocol'],
                'username':obj['parameters']['username'],
                'password':obj['parameters']['password']
            }
    return result
        