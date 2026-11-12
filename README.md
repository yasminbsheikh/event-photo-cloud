# Photo Cloud

**NB! Still under development.**

**Turn your photos into a living slideshow.**

Photo Cloud fills a screen with your photos, floating gently around a black
background like a cloud. Every half minute, two photos glide forward to take
centre stage, then drift back into the crowd. It is perfect for a screen or
projector at a wedding, party, birthday, exhibition or office event.

Your photos can come from:

- 📁 a folder on your computer
- 📦 a **Dropbox** folder
- ☁️ a **Google Drive** folder
- 🖼️ **Google Photos** (photos you pick)

Photo Cloud runs on your own computer. Your photos are not uploaded to us or
to anyone else.

[Link to demo](https://youtu.be/4I56US-AyBU)

> **Status:** Photo Cloud is currently started from a terminal window (see
> "Getting started" below). A simple one-click installer is planned. Anything
> that needs technical know-how is kept in [docs/DEVELOPING.md](docs/DEVELOPING.md).

---

## What you need

- A Windows, Mac or Linux computer connected to the screen you want to show it on
- [Python](https://www.python.org/downloads/) version 3.10 or newer (free)
- A web browser (Chrome, Edge, Firefox or Safari)
- For Dropbox, Google Drive or Google Photos: an account there, and a one-time
  setup (see "Using Dropbox, Google Drive or Google Photos")

---

## Getting started

### 1. Download

Download this project and unzip it, for example to `C:\photo-cloud` on Windows.

### 2. Open a terminal in that folder

- **Windows:** open the folder, click the address bar, type `powershell` and press Enter.
- **Mac:** right-click the folder and choose *New Terminal at Folder*.

### 3. Set up (first time only)

**Windows**
```
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
```
**Mac / Linux**
```
python3 -m venv .venv
source .venv/bin/activate
```

(If Windows says scripts are blocked, type
`Set-ExecutionPolicy -Scope Process RemoteSigned` and press Enter, then try again.)

### 4. Start it

```
python run.py --folder "C:\Users\YourName\Pictures"
```

Your browser opens and the photos start floating. To stop, click the terminal
window and press **Ctrl + C**.

Next time you only need to open the terminal, repeat the "activate" line from
step 3, and run the start command again.

---

## Using the screen

- **Settings:** move your mouse and a small gear ⚙ appears in the top-right
  corner. Click it to choose where photos come from. Press **Esc** to close.
- **Full screen:** press **F11** (Windows/Linux) or **Ctrl + Cmd + F** (Mac) in the browser.
- **Mouse hidden:** after a few seconds without moving, the mouse and gear disappear
  so the screen looks clean.
- **New photos:** open the settings and press **Load / refresh** to pick up photos
  added since you started.

---

## Choosing where photos come from

Open the settings (⚙) and choose **Photo source**:

| Source | What to type |
|---|---|
| **Local folder** | The folder path, for example `C:\Users\YourName\Pictures`. Tick *Include subfolders* to include folders inside it. |
| **Google Photos** | Nothing to type. Press **Choose photos in Google Photos…** and pick the photos you want. |
| **Google Drive folder** | Paste the folder's share link (in Drive: right-click the folder, *Share*, *Copy link*). Leave blank for your whole Drive. |
| **Dropbox folder** | The folder path, for example `/Events/Wedding`. Leave blank for your whole Dropbox. |

Then press **Load / refresh**.

Good to know:
- Only **JPG, PNG and WebP** photos are shown. Phone photos in HEIC format are skipped.
- The first time, photos from Dropbox or Google Drive take a little while to
  download. After that they load quickly.
- **Google Photos is different:** Google no longer allows apps to look through your
  albums. You pick photos in Google's own window, and Photo Cloud keeps that
  selection (up to 200 photos). To change it, pick again.

---

## Using Dropbox, Google Drive or Google Photos

These need a one-time setup and a sign-in:

1. **One-time setup:** create a free "app" with Dropbox or Google so they know
   who is asking for access. This takes a few minutes and is explained step by
   step in [docs/DEVELOPING.md](docs/DEVELOPING.md#cloud-setup). *(A future
   version will skip this step and just show a "Sign in" button.)*
2. **Sign in:** in the settings (⚙) pick your source and press **Connect**. A new
   tab opens where you sign in and click **Allow**. Photo Cloud only asks to
   **read** your files. It cannot change or delete anything.
3. **Stay signed in:** you only need to do this once. Google may ask you to
   sign in again about once a week while the app is still in test mode.

To remove access at any time, press **Disconnect** in the settings.

---

## Using it at an event

**Let guests add their own photos.** The easiest way:

1. In Dropbox on the web, go to **File requests** and create one that saves
   into the folder Photo Cloud is showing.
2. Copy the link and turn it into a QR code with any free QR code maker.
3. Print the QR code or show it on a sign. Guests scan it and upload photos
   from their phones. They do **not** need a Dropbox account.
4. New photos appear on the screen when you press **Load / refresh** in the
   settings (or restart Photo Cloud).

**Tips**
- Do a test run the day before, on the real screen.
- Plug the computer in and turn off sleep mode so the screen stays on.
- Keep around 20-60 photos on screen for a nice cloud. More is fine; Photo
  Cloud shows a random selection of up to 60 at a time.

---

## Troubleshooting

**The settings say "Not set up (see README)".**
Photo Cloud can't find your Dropbox or Google sign-in details. Follow the
one-time setup in [docs/DEVELOPING.md](docs/DEVELOPING.md#cloud-setup) and check
the details are saved in the right place.

**Dropbox says "redirect URI mismatch".**
The address you registered in your Dropbox app has to match exactly. Use
`http://127.0.0.1:8765/oauth/callback` and start Photo Cloud without changing the port.

**The old photos keep coming back.**
Photo Cloud remembers the last source you used. Choose a different source in
the settings and press **Load / refresh**, or close all Photo Cloud terminal
windows and browser tabs and start again.

**"Address already in use" or the page won't open.**
Another copy of Photo Cloud is still running. Close its terminal window (or
press Ctrl + C in it) and start again.

**Google asks me to sign in every week.**
That is normal while the Google app is in test mode.

**My Google Drive folder can't be found.**
Make sure the folder is in, or shared with, the same Google account you connected.

**Some photos are missing.**
Only JPG, PNG and WebP photos are shown, and a random selection of up to 60 at a time.

---

## Your privacy

- Photo Cloud runs only on your computer. Nothing is sent anywhere except to
  Dropbox or Google when you ask it to fetch your own photos.
- It asks for **read-only** access.
- Your sign-in is stored on your computer in a private file (`.photocloud` in
  your user folder) and is never shown in the browser page.
- Downloaded copies are stored in that same folder. Delete them any time with
  `python run.py --clear-cache`.

---

## For developers

How it works, the project layout, running the tests and the plan for a
one-click app are in [docs/DEVELOPING.md](docs/DEVELOPING.md).