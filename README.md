# Bibliothèque HA

Intégration Home Assistant (installable par HACS) qui transforme vos automatisations, scripts,
scènes, helpers, templates et fichiers en **packages réutilisables**, les range dans une
**bibliothèque** (dossier local ou dépôt GitHub) et les **installe sur n’importe quelle autre
instance** en gérant les dépendances.

## Ce que fait le panneau « Bibliothèque »

| Onglet | Rôle |
|---|---|
| **Cette instance** | Scanne l’instance, propose des packages, permet de les renommer, de choisir les contextes (particulier, hôtel, site logistique, bureau), de déplacer un élément d’un package à un autre, puis d’exporter et de publier. |
| **Bibliothèque** | Parcourt une source (locale ou GitHub), filtre par contexte, intégration ou recherche, montre le YAML, les dépendances et les vues de dashboard, et installe un ou plusieurs packages. |
| **Installés** | Liste ce qui a été installé depuis la bibliothèque, signale les mises à jour, désinstalle proprement. |

Dans **Cette instance**, le bouton « Nettoyer… » retire du registre les automatisations, scripts et scènes fantômes (supprimés mais toujours listés comme indisponibles).
| **Réglages** | Nom de l’instance, dépôts GitHub (lecture et publication), règles de regroupement. |

### Ce que le scan lit
- automatisations et scripts (créés dans l’interface, en YAML ou dans des packages) ;
- scènes, helpers (`input_*`, `timer`, `counter`, `schedule`), YAML ou interface ;
- capteurs template (format moderne, ancien format et helpers template de l’interface) ;
- plateformes YAML (`sensor:`, `binary_sensor:`…), `utility_meter`, `shell_command`, `rest_command`, `group`, `command_line`… ;
- fichiers `pyscript/`, `python_scripts/`, `blueprints/` ;
- vues de dashboard et ressources front (cartes HACS).

Les valeurs de `secrets.yaml` sont remises en `!secret nom`. Les identifiants de webhook,
jetons, mots de passe, numéros de téléphone et e-mails écrits en clair deviennent aussi des
`!secret` à renseigner à l’installation.

### Gestion des dépendances
- Chaque définition (helper, template, script…) appartient à **un seul** package : celui qui
  l’utilise le plus. Les autres packages qui en ont besoin le déclarent comme **package requis**,
  installé automatiquement avant eux. Deux packages ne définissent donc jamais le même helper
  (ce qui casserait la fusion des packages de HA).
- Chaque manifeste liste les **intégrations requises**, les **entités à fournir** sur l’instance
  cible, les **cibles de notification** et les **références cassées** sur l’instance d’origine.

### Vues de dashboard
Bibliothèque → Vues de dashboard → choisir un dashboard (mode interface) → **Ajouter à ce dashboard**. La vue est ajoutée à la fin avec vos correspondances d’entités, après une sauvegarde du dashboard dans `/config/ha_library/backups/`. Les cartes `custom:` et entités manquantes sont signalées.

### Installation d’un package
1. Plan : intégrations (chargée / à configurer / absente), correspondance des entités avec
   suggestions, choix du service de notification, secrets à saisir, conflits.
2. Écriture dans `/config/packages/bibliotheque/bibliotheque_<id>.yaml` (et des fichiers
   pyscript/blueprints), avec vos entités à la place de celles d’origine.
3. Vérification complète de la configuration : si un problème apparaît, **tout est annulé**.
4. Rechargement des domaines concernés sans redémarrer quand c’est possible.

Une définition qui existe déjà sur l’instance cible (même helper, même identifiant
d’automatisation) est conservée et signalée. Si les packages ne sont pas activés, la
bibliothèque peut ajouter `packages: !include_dir_named packages` à `configuration.yaml`
(une sauvegarde est créée).

À la désinstallation, le fichier est supprimé, les domaines rechargés et les entrées du
registre laissées orphelines sont nettoyées.

## Installation

### Par HACS (dépôt personnalisé)
1. HACS → ⋮ → **Dépôts personnalisés** → URL de ce dépôt, catégorie **Intégration**.
2. Installez « Bibliothèque HA », redémarrez Home Assistant.
3. Paramètres → Appareils et services → **Ajouter une intégration** → « Bibliothèque HA ».
4. Le panneau **Bibliothèque** apparaît dans la barre latérale (administrateurs uniquement).

### Manuellement
Copiez `custom_components/ha_library` dans `/config/custom_components/`, redémarrez, puis
ajoutez l’intégration.

## Bibliothèque centrale sur GitHub
1. Créez un dépôt **privé** vide (par ex. `ma-bibliotheque-ha`).
2. Créez un jeton GitHub *fine-grained* limité à ce dépôt, permission **Contents : Read and write**.
3. Réglages → Dépôts GitHub : ajoutez le dépôt et le jeton, cochez « Publication ».
4. Sur l’instance source : Cette instance → Scanner → Exporter → **Publier sur GitHub**.
5. Sur une autre instance : ajoutez le même dépôt (jeton en lecture suffisant) →
   Bibliothèque → choisissez la source → **Télécharger la dernière version** → Installer.

Format d’une bibliothèque : `library.json`, `packages/<id>/{package.yaml, manifest.json, items.json, files/}`, `views/<id>.yaml`.

## Règles de regroupement
Sans règle, les packages sont formés par catégorie HA, puis par préfixe commun des noms
(« Dreame • … »), puis par premier mot commun, puis par éléments qui partagent des helpers.
Des règles (Réglages) forcent un regroupement, un titre, une description et des contextes.
Exemple complet : [`examples/regles-maxime.yaml`](examples/regles-maxime.yaml).

## Limites connues
- Les déclencheurs « appareil » (`device_id`) sont signalés mais restent à refaire sur l’instance cible.
- Les entités créées par une intégration (Tuya, ZHA, Dreame…) ne s’installent pas : elles sont listées dans « Entités à fournir ».

## Développement
```bash
pip install pytest-homeassistant-custom-component
pytest -q
```
`tools/convert_browser_export.py` analyse hors ligne un export JSON fait depuis le navigateur.
