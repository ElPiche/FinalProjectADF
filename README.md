# FinalProjectADF
Proyecto final tecnólogo en informática Framework de detección de anomalías
[Parking Lot](https://docs.google.com/document/d/1zOSzxRsrPZe7DSr-DHhbfsDFXiPR3SI07RYdtVkiDpQ/edit?tab=t.0#heading=h.yzf6b27f5gn7)

[Diagrama](https://app.diagrams.net/#G1OnaDn2s1fRY0rvP8RLPCqJ3RhfiUmgje#%7B%22pageId%22%3A%2234t6jlsbtPh1E6wETkqf%22%7D)

[Jira](https://braian-granero.atlassian.net/jira/software/projects/KAN/boards/1)


## Setup 

### Infraestructura principal
docker-compose up -d

### Servicio extractor
docker-compose -f extractor/docker-compose.yml up -d

### Toda le infraestructura junta __(no funciona por el momento)__
~~docker-compose -f docker-compose.yml -f extractor/docker-compose.yml up -d~~