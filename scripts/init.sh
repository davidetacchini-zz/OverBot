#!/bin/bash
red=$(tput setaf 1)
green=$(tput setaf 2)
bold=$(tput bold)
reset=$(tput sgr0)

if [ "$EUID" -ne 0 ]; then 
	echo "${red}You must have root permission.${reset}"
  	exit 1
else
 	echo "[${green}OK${reset}] root permissions"
fi

printf "${bold}Welcome to the OverBot Setup!${reset}\n\n"

printf "Checking for the database ${bold}overbot${reset} to exists...\n"
if [ "$( psql overbot -tAc 'SELECT 1' 2>&1 )" = '1' ]; then
    printf "[${green}OK${reset}] Database ${bold}overbot${reset} exists.\n"
else
    printf "${red}Database overbot doesn't exists. Please follow all the README instructions.${reset}\n"
    exit 1
fi

printf "Checking for the configuration file to be installed..."
if [ ! -f "./config.example.py" ]; then
	printf "\nInstalling the configuration file...\n"
	curl https://raw.githubusercontent.com/davidetacchini/overbot/master/config.example.py -o config.py
	printf "[${green}OK${reset}] configuration file successfully installed.\n"
else
    printf "Renaming config.example.py to config.py...\n"
    mv config.example.py config.py
fi

printf "Copying service file to /etc/systemd/system/overbot.service...\n"
sed -i "s:/path/to/overbot/:$(pwd)/:" overbot.service
sed -i "s:username:$(whoami):" overbot.service
cp overbot.service /etc/systemd/system/overbot.service

printf "Loading database schema...\n"
sudo -u davide psql overbot < schema.sql

printf "Reloading the daemon...\n"
{
	sudo systemctl daemon-reload
} || {
	echo "[${red}ERROR${reset}] an error occured while reloading the daemon."
}

printf "${green}${bold}Installation completed!${reset}${reset}\n"
printf "${red}Checkout the README file to complete the installation.${reset}\n"
