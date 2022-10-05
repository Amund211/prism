# Prism

![Using Prism](./images/in_queue.png)

## Download
[CLICK HERE](../../releases/latest) to go to the latest release.
Your browser might tell you that the file is potentially dangerous, but you can safely ignore this warning.
See the section on [safety](#safety) for more info.

## Description
Prism is an open source stats overlay for Hypixel Bedwars (not associated).
Prism will detect the players in your lobby as they join and when you type `/who`, and automatically show you their stats.
The overlay can be extended with the [Antisniper API](https://antisniper.net) (not associated) to denick some nicked players and display estimated winstreaks.

## Qualities
- Automatic party and lobby detection
- Good players sorted to the top and highlighted in red
- Fast
- Denicking (with Antisniper API)
- Winstreak estimates (with Antisniper API)

## Tips
- Enable autowho so you don't have to type `/who` when you join a filled queue
- Follow the instructions in the settings page to add an Antisniper API key to get denicking and winstreak estimates
- Click on the pencil next to a nicked teammate to set their username

## Safety
Being open source, anyone can look at the source code for Prism to see that nothing nefarious is happening.
The released binaries are created using `pyinstaller` in GitHub Actions from a clean clone of the repository.
If you do not trust the released binary you can clone the project and run it from source by installing the dependencies and running `python prism_overlay.py` from the project root.
