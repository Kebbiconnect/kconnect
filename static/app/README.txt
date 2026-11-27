KPN ANDROID APP DOWNLOAD SLOT
=============================

The Download App page (/download-app/) serves the file in this
folder. To publish or update the Android app download:

1. Build the SIGNED RELEASE APK of the KPN app.
   Never place a debug build here.
2. Name the file exactly:

       kpn-app.apk

   and put it in this folder (static/app/), replacing any older
   copy. The download link never changes, so the footer link,
   shared links and the Download App page keep working.
3. Optional: add a plain-text file named VERSION.txt in this
   folder containing just the version, for example:

       1.0.0

   The Download App page shows it next to the download button,
   together with the real file size.
4. Push and redeploy the website. collectstatic copies the APK
   into the served static files, and /download-app/apk/ streams
   it to phones as an attachment.

If kpn-app.apk is absent, the Download App page shows a plain
"available soon" notice instead of a download button, and the
/download-app/apk/ address returns 404.
