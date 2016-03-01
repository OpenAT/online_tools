# online_tools
Tools for FS-Online

# Installation neuer Instanzen

1. Github instance-repository anlegen (z.B.: ahch)
  - default brach: o8
  - instance.ini (mit korrektem core)
  - .gitignore (server.conf, /update ...)
2. Instanz Pillar Datei anlegen
  - Passwörter ändern
  - Hosts kontrollieren
3. Orchestrate Runner starten (wegen ssh key)
4. Github deploy key einreichten für Instanz Repo
5. Orchestrate Runner starten (finale einrichtung)
   - oder: salt 'online?' state.highstate
6. Update Webhook einrichten
   - salt master datei
   - github webhook

# Installation neuer minions

1. minion aufsetzten
2. saltstack installieren
3. minion id anpassen 
4. minion_roles korrekt setzen
5. key im saltstack-master akzeptieren
6. openat user löschen (oder wir machen das gleich in ubuntu1404.sls)

# Installation am Entwicklungsrechner (Mac)

1. Ordner "online" anlegen
2. Clone online_tools repo in den Ordner "online" ```..../online/online_tools```
3. Clone Instanz-Repo in den ordner "online" ```..../online/dadi```
4. Ausführen der Instanz mit --update: ```..../online/online_tools/start.py --instance-dir ..../online/dadi --update```
  - Automatisch: clone dadi repo o8 to ```..../online/dadi/update/dadi_update```
  - Automatisch: clone core to ```..../online/online_o8r?```
5. Datenbank wiederherstellen für dadi UND! dadi_update
  - ```..../online/online_tools/start.py --instance-dir ..../online/dadi(/update/dadi_update) --restore ..../folder_of_backup```

ACHTUNG: Am Entwicklungsrechner wird ```..../online/dadi``` nicht automatisch nach einem Update aktualisiert. 
Muss, wenn gewünscht, händisch vorgenommen werden.
