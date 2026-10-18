# Scoped Cortex trust

`emotiv-rootCA.pem` is the public EMOTIV Root CA downloaded from the certificate linked in [official Cortex documentation](https://emotiv.gitbook.io/cortex-api/connecting-to-the-cortex-api):

https://raw.githubusercontent.com/Emotiv/cortex-example/master/certificates/rootCA.pem

Downloaded October 17, 2026. SHA-256:

`EC4A5B709CAC733D8683573C843BA831001C5CA101CA152FC0D4A7CD0E301CC6`

This public certificate contains no private key. Only `backend/cortex.py` loads it into a dedicated client SSL context. It does not alter the operating system trust store, disable verification, or change any global TLS setting. Hostname verification is retained for `localhost`. The local verified probe succeeded against Cortex 4.13.5.3. Review any future CA replacement against the official vendor source.
