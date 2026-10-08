# AMB Boutique | YouTube Cloud Publisher

**Drive autorizado:** alanantonioshopify@gmail.com (somente essa conta).

**YouTube:** @AMBB.OUTIQUE (ID verificado a cada execução).

O fluxo de publicação usa Google Drive como fila, GitHub Actions como executor remoto e YouTube Data API. Funciona com o Mac desligado. A execução é agendada de 15 em 15 minutos, sem promessa de pontualidade exata.

## Ativação inicial (no Mac, somente uma vez)
No Mac, executar `~/AMB-YouTube-Autoposter/venv/bin/python ~/AMB-YouTube-Autoposter/cloud/bootstrap_once.py` e aprovar a conta **alanantonioshopify@gmail.com** e o canal **@AMBB.OUTIQUE** no Google. O script impede a autorização com conta diferente, cria as pastas na conta correta e grava credenciais em **GitHub Secrets**, sem incluí-las no repositório.

Se houver um bloqueio da aplicação no OAuth, configurar a tela de consentimento e adicionar a conta como testadora no projeto Google Cloud correto. Tokens de aplicativos no modo *Testing* expiram em cerca de 7 dias. Para operação permanente é necessário publicar o app e, se exigido, cumprir a verificação Google. A YouTube Data API também pode restringir vídeos enviados com um projeto não auditado ao modo privado; publicar na API não garante publicidade.

## Pasta do Drive (criada após autorização)
- PRONTOS PARA PUBLICAR: arquivos inéditos .mp4, .mov, .m4v, .webm, .jpg, .jpeg ou .png
- PUBLICADOS: uploads que retornaram public
- ERROS E REVISAO: uploads potencialmente duplicados, privados ou com falha

Apenas a pasta PRONTOS é processada, do vídeo/imagem mais recente para os anteriores. Um arquivo por execução. Imagens estáticas são convertidas em vídeo vertical de 12 segundos, não em carrossel do Instagram. Nomes dos arquivos alimentam o título e descrição básica em inglês com o site https://ambboutique.online. Para SEO específico por produto, evoluir metadados em uma etapa posterior. O gerador não analisa visualmente os criativos, por isso nomes descritivos são importantes.

A cada envio, o arquivo é marcado `inflight` **antes** do upload; estados incertos são enviados para revisão, não publicados novamente automaticamente. Não há posts cruzados no Instagram nesta versão.

## Segurança
- Nenhuma credencial real neste repositório.
- Sem contas Google diferentes do Drive AMB.
- Publicação desligada até que `AUTO_PUBLISH_ENABLED=true` seja instalado, só depois de autenticar as identidades corretas.
- O GitHub Actions fica sem acesso ao Mac e ao restante dos arquivos do Drive, exceto conforme os escopos concedidos pelo Google.
- A OAuth Drive scope usada pela versão inicial é `drive` (acesso amplo ao Drive da conta), portanto avaliar escopos mais restritos após validar as necessidades.
- O Google Cloud OAuth client JSON fica só no Mac. Um `refresh_token` é armazenado em GitHub Actions Secrets.
