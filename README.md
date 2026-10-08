# AMB Boutique | Publicação automática no YouTube

Esta automação roda **no GitHub Actions**, verifica o **Google Drive da conta alanantonioshopify@gmail.com** e envia somente para **@AMBB.OUTIQUE**. Funciona com o Mac desligado. O agendamento é feito em intervalos aproximados de 15 minutos (o GitHub pode atrasar execuções).

## Onde colocar seus arquivos

**SHORTS - PARA POSTAR**
https://drive.google.com/drive/folders/19fvzAwEVJ1YsC4mFkDYFLO_jlKRP9Rz7

- Coloque somente **vídeos verticais** (.mp4, .mov, .m4v, .webm) de até 3 minutos.
- Cada vídeo é publicado como Short, quando aceito pela classificação do YouTube.
- Não precisa adicionar uma imagem separada para a thumbnail.
- Após a publicação, o vídeo é movido para **POSTADO / SHORTS**.

**VIDEOS HORIZONTAIS - PARA POSTAR**
https://drive.google.com/drive/folders/1YsFjiu_4dbv81d69Bhakq4B1DYaVoMNd

- Coloque um vídeo horizontal e uma thumbnail (.jpg, .jpeg ou .png) **com o mesmo nome-base**.
- Exemplo: `Mabel_Print_Dress.mp4` + `Mabel_Print_Dress.jpg`.
- Thumbnail recomendada: 1280 × 720 px, proporção 16:9, boa qualidade e sem bordas.
- Sem thumbnail correspondente, o vídeo **aguarda** e não é publicado.
- Após upload e aplicação da thumbnail, os dois arquivos vão para **POSTADO / VIDEOS HORIZONTAIS**.

**POSTADO**: https://drive.google.com/drive/folders/1wkVdcYq8eEEYaw2gfbgebn7Y9n9e8dfe

**ERROS E REVISAO**: https://drive.google.com/drive/folders/1LkeBpftvV85fwIzwDhtSX3fiSAn1a8zH

## Regras de segurança e fila

1. Somente as duas pastas **PARA POSTAR** são monitoradas. A pasta antiga PRONTOS PARA PUBLICAR não está mais ligada a este publicador.
2. Os arquivos novos são analisados por ordem de modificação, um vídeo elegível por execução.
3. Com as pastas vazias, **não acontece nenhuma publicação**.
4. A ferramenta verifica proporção e duração antes do upload. Se estiver inválido, o vídeo vai para revisão.
5. A thumbnail horizontal é aplicada pela YouTube Data API depois do upload. Se a aplicação falhar, o vídeo já pode existir no YouTube; por segurança, os arquivos vão para revisão com o ID da publicação, sem repetir o envio automaticamente.
6. Só move para **POSTADO** quando o YouTube confirma a publicação como pública e, se horizontal, confirma a thumbnail.
7. Os títulos são montados automaticamente a partir do **nome do arquivo** em inglês, com descrição básica, hashtags e endereço https://ambboutique.online. Escreva nomes de produtos claros para melhorar os títulos. A ferramenta não interpreta o vídeo para inventar características.
8. O Google OAuth está em modo de testes. Um refresh token de teste pode expirar após cerca de 7 dias. Para operação contínua, regularizar a aplicação Google. O YouTube também pode restringir a privacidade de uploads de projetos não auditados.
9. Não copie credenciais OAuth ou outras senhas para o Drive. O token permanece em **GitHub Actions Secrets**.
10. Para interromper novas publicações, defina o segredo do repositório `AUTO_PUBLISH_ENABLED` como `false`.

## Diagnóstico
GitHub Actions: https://github.com/andreajoa/amb-boutique-cloud-publisher/actions

Os logs informam se não existe vídeo, se falta thumbnail e quais arquivos foram postados. O teste automático está em `test_publisher.py`.
