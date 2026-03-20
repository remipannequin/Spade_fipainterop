# Interoperabilité de jade avec d'autres plateformes

## Test 1: JADE <--> JADE

On cherche à faire communiquer deux agents chacun sur une plateforme Jade.

### Mise en place

Les plateformes doivent être configurées pour écouter sur des ports TCP différents. Il
y en a deux : le port pour la communication interne (IMTP, par défaut 1099), et celui
qui est utilisé pour le MTP HTTP (par défaut 7778).

Un script `launch_jade.sh` est écrit. Il se carge de copier les dépendances déclarées
dans le `pom.xml`, puis de lancer java avec les options appropriées, et enfin de 
configurer les numéro de ports.

En particulier, il faut ajouter les options

```
  --add-exports java.xml/com.sun.org.apache.xerces.internal.jaxp=ALL-UNNAMED \
  --add-opens java.xml/com.sun.org.apache.xerces.internal.jaxp=ALL-UNNAMED \
```

pour éviter une erreur au chargement de la bibliothèque XML d'encodage/décodage des
messages.

### Ajout de pateforme 2 à plateforme 1

On utilise l'ajout par RMA. Il faut saisir en particulier l'adresse http de la plateforme
distante (par exemple <http://localhost:7771/JADE>).

### Échange de message

On utilise des DummyAgents sur chaque plateforme pour envoyer/recevoir des message.

Il faut saisir l'adresse de la plateforme distante dans le champ adresse du message.
Avec les sniffeur, on constate que seul le message envoyé est detecté (pas le message
reçu).

Lors de la réponse, pas besoin de resaisir l'adresse du destinataire, qui est
automatiquement ajoutée quand la réponse est crée.

La déclaration d'un plateforme distance dans le RMA n'est pas requise pour l'envoi
de message. Il suffit d'avoir la bonne adresse.

Si le HAP (la partie derriere le @) n'est pas précisé ou bien est incorect,
l'envoi échoue avec "AgentNotFound" (le message d'erreur est envoyé par l'AMS).

