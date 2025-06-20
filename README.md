# KCM to PAM conversion script

Allows you to convert KCM connections to a PAM framework, in one of two ways:  
- Using the KCM JSON export available here.
  - It can run this export for you if you are running this script from the KCM host.
- Using existing KCM connection records if you're using Dynamic Tokens.
  - If there is a hostname and port on the record, it will be used, else a default '1.1.1.1:22' hostname will be created.

Supports the use of an existing KSM application / gateway.

Required dependencies:  
```
pip install keepercommander
```  
For the internal JSON export:  
```
pip install mysql-connector-python
pip install pyYAML
```
