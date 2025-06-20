from keepercommander.params import KeeperParams
from keepercommander import api
from keepercommander import cli
from keepercommander.commands.pam import config_helper

from json import load, loads
from kcm_export import run_kcm_export, unpack_export

protocols = {
    '3389':'rdp',
    '2179':'rdp',
    '22':'ssh',
    '2222':'ssh',
    '5900':'vnc',
    '5901':'vnc',
    '23':'telnet',
    '8080':'kubernetes',
    '3306':'mysql',
    '5432':'postgresql',
    '1433':'sql-server',
}


def cli_prompts():
    commander_usr = input('User email: ')
    shared_folders = []

    method = input('''Which method do you want to use?
    1. Leverage the KCM JSON export to build a PAM framework.
    2. Convert one or more KCM shared folders into a PAM framework.
    Input: ''')
    while method not in ['1','2']:
        method = input('''Please enter one of the options below:
        1. Leverage the KCM JSON export to build a PAM framework.
        2. Convert one or more KCM shared folders into a PAM framework.
        Input: ''')
    

    if method == '1':
        export_method = input('''How do you wish to feed the JSON data?
        1. I'm running this on the KCM host and would like this program to export the data directly.
        2. I have already exported my KCM data to a JSON file I wish to use.
        Input: ''')
        while export_method not in ['1','2']:
            export_method = input('''Please enter one of the options below:
            1. I'm running this on the KCM host and would like the data exported directly from here.
            2. I have already exported my KCM data to a JSON file I wish to use.
            Input: ''')
    
        if export_method == '1':
            json_data = run_kcm_export()
        elif export_method == '2':
            success = False
            while not success:
                file_path = input('Enter the full path of the JSON file (or just the filename if in the same directory as this program): ')
                if '\\' in file_path: # Handle windows path escapes
                    file_path = file_path.replace('\\','\\\\')
                try:
                    with open(file_path,'rb') as file:
                        shared_folders = unpack_export(load(file))
                    success = True
                except Exception as e:
                    print(e)
            
    if method == '2':
        shared_folders_complete = False

        while not shared_folders_complete:
            shared_folder_prompt = input('Enter a KSM shared folder name (enter / if all shared folders added): ')
            if shared_folder_prompt == '/':
                print(shared_folders)
                confirm = input('Are all these folder names valid and unique? (y/n) ')
                if confirm.lower() == 'y':
                    shared_folders_complete = True
                elif confirm.lower() == 'n':
                    print('Restarting...')
                    shared_folders = []
                else:
                    print('WrongWrong input')
            else:
                shared_folders.append(shared_folder_prompt)        
    
    prompt_data = {
        'method':method,
        'commander_usr':commander_usr,
        'shared_folders':shared_folders,
    }
    return prompt_data
    
    
def commander_login(commander_usr):
    print('Logging into Commander...')
    
    my_params = KeeperParams()
    my_params.user = commander_usr
    api.login(my_params)
    api.sync_down(my_params)
    
    return my_params


def setup_pam(my_params, gateway_folder_name, app_folder_uids):
    app, gateway = None, None
    
    existing_app = input("Would you like to use an existing KSM application? (y/n) ")
    if existing_app.lower() == 'y':
        cli.do_command(my_params, 'sm app list')
        app = input('Please copy the app UID here: ')
        existing_gateway = input("Would you like to use an existing gateway (must be attached to your existing app)? (y/n) ")
        if existing_gateway.lower() == 'y':
            cli.do_command(my_params, 'pam g list')
            gateway = input('Please copy the gateway UID here: ')
        
    if not app:
        print('Creating application...')
        cli.do_command(my_params, f"sm app create '{gateway_folder_name}'")
        app = gateway_folder_name
        
    for uid in app_folder_uids:
        cli.do_command(my_params, f"sm share add -a='{app}' -s '{uid}' --editable")
    
    if not gateway:
        print('Creating gateway...')
        cli.do_command(my_params, f"pam gateway new -n '{gateway_folder_name}' -a '{app}' --c b64")
        gateway = gateway_folder_name
        
    return app, gateway


def convert_kcm_to_pam(data):
    commander_usr = data['commander_usr']
    shared_folders = data['shared_folders']
    
    my_params = commander_login(commander_usr)
    
    print('Creating new PAM folder directory...')
    gateway_folder_name = 'PAM KCM conversion'
    cli.do_command(my_params, f"mkdir '{gateway_folder_name}' -uf")
    for folder in shared_folders:    
        cli.do_command(my_params, f"mkdir '{gateway_folder_name}/_converted_ {folder} Resources' -sf")
        cli.do_command(my_params, f"mkdir '{gateway_folder_name}/_converted_ {folder} Users' -sf")
    app_folder_uids = []
    user_folder_uids = []
    for folder in api.search_shared_folders(my_params, '_converted_'):
        app_folder_uids.append(folder.shared_folder_uid)
        if folder.name[-5:]=='Users':
            user_folder_uids.append(folder.shared_folder_uid)
    print('Done.')
          
    app, gateway = setup_pam(my_params, gateway_folder_name, app_folder_uids)
    
    print('Setting up PAM configurations and connection records...')
    for folder in shared_folders:
        cli.do_command(my_params, 
f"pam config new -t '{folder}' -g='{gateway}' -sf '{gateway_folder_name}/_converted_ {folder} Users' -env local --connections on --rotation off ")
        
        for record in shared_folders[folder]:
            if shared_folders[folder][record]['protocol'] == 'http':
                pass
            else:
                title = record
                login = shared_folders[folder][record]['username']
                password = shared_folders[folder][record]['password']
                hostname = shared_folders[folder][record]['hostname']
                port = shared_folders[folder][record]['port']
                protocol = shared_folders[folder][record]['protocol']
                    
                cli.do_command(my_params, 
        f"record-add -t '{title}' -rt pamUser login='{login}' password='{password}' --folder='{gateway_folder_name}/_converted_ {folder} Users'")
                cli.do_command(my_params, 
        f"record-add -t '{title}' -rt pamMachine pamHostname='{hostname}:{port}' --folder='{gateway_folder_name}/_converted_ {folder} Resources'")

                config = ''
                config_list = config_helper.pam_configurations_get_all(my_params)

                for obj in config_list:
                    if loads(obj['data_unencrypted'].decode('utf8'))['title'] == folder:
                        config = obj['record_uid']
                cli.do_command(my_params, 
    f"pam connection edit -c '{config}' -a '{gateway_folder_name}/_converted_ {folder} Users/{title}' '{gateway_folder_name}/_converted_ {folder} Resources/{title}' -p={protocol} -cn on")
        
    print('Conversion finished.')


def convert_folders_to_pam(data):
    commander_usr = data['commander_usr']
    shared_folders = data['shared_folders']
    
    my_params = commander_login(commander_usr)
    
    print('Unpacking shared folder data...')
    
    keeper_folders = {}
    for folder_name in shared_folders:
        folder = api.search_shared_folders(my_params,folder_name)[0]
        keeper_folders[folder_name] = {
            'folder_data': folder,
            'records': folder.records
            } 
    print('Creating new PAM folder directory...')
    gateway_folder_name = 'PAM KCM conversion'
    cli.do_command(my_params, f"mkdir '{gateway_folder_name}' -uf")
    for folder in keeper_folders:    
        cli.do_command(my_params, f"mkdir '{gateway_folder_name}/_converted_ {folder} Resources' -sf")
        cli.do_command(my_params, f"mkdir '{gateway_folder_name}/_converted_ {folder} Users' -sf")
    app_folder_uids = []
    user_folder_uids = []
    for folder in api.search_shared_folders(my_params, '_converted_'):
        app_folder_uids.append(folder.shared_folder_uid)
        if folder.name[-5:]=='Users':
            user_folder_uids.append(folder.shared_folder_uid)
    print('Done.')
          
    app, gateway = setup_pam(my_params, gateway_folder_name, app_folder_uids)
    
    print('Setting up PAM configurations and connection records...')
    for folder in keeper_folders:
        cli.do_command(my_params, 
f"pam config new -t '{folder}' -g='{gateway}' -sf '{gateway_folder_name}/_converted_ {folder} Users' -env local --connections on --rotation off ")
        
        for record in keeper_folders[folder]['records']:
            record_data = api.get_record(my_params, record['record_uid'])
            title = record_data.title
            login = record_data.login
            password = record_data.password
            hostname = record_data.get('text:Hostname')
            port, protocol = '',''
            if not hostname:
                hostname = record_data.get('host:')['hostName']
                port = record_data.get('host:')['port']
                protocol = protocols[str(port)] if port in protocols else '' 
            if not port:
                hostname = '1.1.1.1'
                port = '22'
                protocol = 'ssh'
                
            cli.do_command(my_params, 
    f"record-add -t '{title}' -rt pamUser login='{login}' password='{password}' --folder='{gateway_folder_name}/_converted_ {folder} Users'")
            cli.do_command(my_params, 
    f"record-add -t '{title}' -rt pamMachine pamHostname='{hostname}:{port}' --folder='{gateway_folder_name}/_converted_ {folder} Resources'")
            
            config = ''
            config_list = config_helper.pam_configurations_get_all(my_params)

            for obj in config_list:
                if loads(obj['data_unencrypted'].decode('utf8'))['title'] == folder:
                    config = obj['record_uid']
            cli.do_command(my_params, 
f"pam connection edit -c '{config}' -a '{gateway_folder_name}/_converted_ {folder} Users/{title}' '{gateway_folder_name}/_converted_ {folder} Resources/{title}' -p={protocol} -cn on")
    
    print('Conversion finished.')
