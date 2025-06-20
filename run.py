from kcm_to_pam import cli_prompts, convert_folders_to_pam, convert_kcm_to_pam


# RUNTIME CODE
data = cli_prompts()
if data['method'] == '1':
    convert_kcm_to_pam(data)
elif data['method'] == '2':
    convert_folders_to_pam(data)