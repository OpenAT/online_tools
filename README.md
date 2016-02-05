# online_tools
Tools for FS-Online

# Update Reihenfolge

Diese Reihenfolge ist bei instanz updates unbedingt einzuhalten:

1. Lokales herunterladen des target odoo sources und des instance dirs
2. ändern des targets in der version.ini
3. lokaler updateversuch
4. bei erfolg commit der version.ini
5. push to github und anlage eines neuen release tags für das instance repo e.g. dadi -> o8r1
6. der tag löst einen webhook aus der den server online1 informiert und
  - git fetch git pull im ordner dadi macht
  - das odoo service dadi neu startet
7. das startup script erledigt beim service neustart den rest
8. Menschliche überprüfung ob die Webseite noch genauso ausshieht wie vorher und ob die instanz rennt

Optional: Die pre-backup Updates werden nicht automatisch gelöscht - dies muss von zeit zu zeit getan werden.

Vorteile:
- Ich muss nicht physikalisch auf den produktiven Server sein um updates einzuspielen
- Automatische Pre-Update Backups
- Autmomatische Wiederherstellung des Pre-Update Backups bei Update Fehlern
- Update Log
- Klare Information über den odoo_source einer instanz
- Klare Infomration über den minimum benötigten odoo source für die instanz-addons

subprocess32.CalledProcessError: Command '['pg_restore', '--no-owner', '--dbname=postgresql://vagrant:vagrant@127.0.0.1:5432/dadi', '/Users/mkarrer/Entwicklung/github/online/dadi/backup/dadi-backup/db.dump']' returned non-zero exit status 1

pg_restore --no-owner --dbname=postgresql://vagrant:vagrant@127.0.0.1:5432/dadi /Users/mkarrer/Entwicklung/github/online/dadi/backup/dadi-backup/db.dump
