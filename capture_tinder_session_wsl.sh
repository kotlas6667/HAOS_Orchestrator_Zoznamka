#!/usr/bin/env bash
# WSL capture je nespolahlivy (sede okno / Chrome for Testing).
# Pre HAOS pouzi noVNC priamo v Tinder add-one — pozri tinder_bot/HAOS_LOGIN.md
echo ""
echo "============================================================"
echo " WSL capture NEPouzivaj pre HAOS."
echo " Windows/WSL cookies sa na Linux Chromium nedešifruju."
echo ""
echo " Spravne riešenie (priamo na HAOS):"
echo "   1) git pull v /addons/haos_tinder && Rebuild add-onu"
echo "   2) V .env: TINDER_HEADLESS=false"
echo "   3) Start add-onu"
echo "   4) Otvor http://192.168.1.109:6080/vnc.html"
echo "   5) Telefon + OTP v Chromium okne"
echo "   6) Po Login detected -> TINDER_HEADLESS=true, restart"
echo ""
echo " Detail: tinder_bot/HAOS_LOGIN.md"
echo "============================================================"
exit 1
