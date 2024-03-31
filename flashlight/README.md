<h1 align="center">Flashlight</h1>


## Description
Flashlight is a proxy to the Hypixel API (not associated) built as the backend for the [prism overlay](https://github.com/Amund211/prism).
Prism is an open source stats overlay for Hypixel Bedwars.

Flashlight is a Google Cloud function.
The version of flashlight hosted by me on Google Cloud is solely intended to be the backend for prism and does not support third party traffic, which is required by the Hypixel API ToS.
Flashlight the software project, however, is permissively licensed, and contributions, changes, use, and re-use are encouraged!

## Running flashlight locally
Note: make sure you have a recent version of go installed.

### Clone the repository
```bash
git clone https://github.com/Amund211/flashlight
cd flashlight
```

### Add your Hypixel API key
```bash
echo 'export HYPIXEL_API_KEY=<your-key-here>' > cmd/.env
```

### Run flashlight
```bash
./cmd/run.sh
```

### Test it
```bash
curl 'localhost:8123?uuid=<some-uuid>'
```

## Creator info
IGN: `Skydeath` \
UUID: `a937646b-f115-44c3-8dbf-9ae4a65669a0`

[discord-invite-link]: https://discord.gg/k4FGUnEHYg
