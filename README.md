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
