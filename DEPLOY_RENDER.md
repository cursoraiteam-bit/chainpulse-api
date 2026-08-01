# Deploy no Render.com — Passo a passo

## 1. Criar o serviço

1. Entra em https://dashboard.render.com
2. **New +** → **Web Service**
3. Conecta o repositório GitHub: `chainpulse-api` (ou o nome que eu criei)
4. Configura:
   - **Name:** chainpulse-api
   - **Region:** Oregon (US West)
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python server.py`
   - **Instance Type:** Free
5. Clica **Create Web Service**

## 2. Esperar o deploy

- Render vai buildar e subir (~2 min)
- Status fica **Live** (verde)
- URL fica tipo: `https://chainpulse-api-xxxx.onrender.com`

## 3. Testar

```
https://SUA-URL.onrender.com/health
https://SUA-URL.onrender.com/dashboard
```

## 4. Me passa a URL

Assim que tiver a URL, me manda. Eu faço:
- Build NPM com essa URL
- Publish no npm
- Build .exe com ícone
- Atualizo o campaign kit

## Nota sobre sleep

No plano free, o serviço **dorme após 15 min** sem tráfego.
O primeiro request depois de dormir demora ~30s (cold start).
Pra manter acordado, use um uptime robot grátis:
https://uptimerobot.com → monitor HTTP a cada 5 min no /health
