#!/bin/bash
# Gera o pacote .deb do Desligamento Inteligente.
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

APP_NAME="desligamento-inteligente"
VERSION="1.3"
MAINTAINER="Jackson Quequi <Jackson-077@users.noreply.github.com>"
HOMEPAGE="https://github.com/Jackson-077/Desligamento-Inteligente"

MAIN_SCRIPT="desligamento.py"
ICON="icon.png"
BUILD="pkg_build"
OUT="${APP_NAME}_${VERSION}_all.deb"

for f in "$MAIN_SCRIPT" "$ICON"; do
    [ -f "$f" ] || { echo "Erro: arquivo '$f' não encontrado." >&2; exit 1; }
done
command -v dpkg-deb >/dev/null || { echo "Erro: dpkg-deb não encontrado." >&2; exit 1; }

# Mantém a versão do código em sincronia com a do pacote
if ! grep -q "^VERSION = \"$VERSION\"" "$MAIN_SCRIPT"; then
    echo "Aviso: VERSION do $MAIN_SCRIPT difere de $VERSION." >&2
fi
python3 -m py_compile "$MAIN_SCRIPT"
rm -rf __pycache__

echo "==> Gerando pacote .deb ($OUT)..."

trap 'rm -rf "$BUILD"' EXIT
rm -rf "$BUILD"
umask 022

install -d -m 755 \
    "$BUILD/DEBIAN" \
    "$BUILD/usr/bin" \
    "$BUILD/usr/share/$APP_NAME" \
    "$BUILD/usr/share/applications" \
    "$BUILD/usr/share/icons/hicolor/512x512/apps"

# Programa e ícones
install -m 755 "$MAIN_SCRIPT" "$BUILD/usr/share/$APP_NAME/$MAIN_SCRIPT"
install -m 644 "$ICON" "$BUILD/usr/share/$APP_NAME/icon.png"
install -m 644 "$ICON" "$BUILD/usr/share/icons/hicolor/512x512/apps/$APP_NAME.png"

# Launcher
cat > "$BUILD/usr/bin/$APP_NAME" << EOF
#!/bin/sh
exec python3 /usr/share/$APP_NAME/$MAIN_SCRIPT "\$@"
EOF
chmod 755 "$BUILD/usr/bin/$APP_NAME"

# Atalho no menu
cat > "$BUILD/usr/share/applications/$APP_NAME.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Desligamento Inteligente
GenericName=Agendador de desligamento
Comment=Agende o desligamento do computador
Comment[pt_BR]=Agende o desligamento do computador
Exec=$APP_NAME
Icon=$APP_NAME
Terminal=false
Categories=System;Utility;
Keywords=desligar;shutdown;timer;agendar;
StartupNotify=true
StartupWMClass=${APP_NAME^}
EOF
chmod 644 "$BUILD/usr/share/applications/$APP_NAME.desktop"

# Metadados
INSTALLED_SIZE=$(du -sk "$BUILD/usr" | cut -f1)
cat > "$BUILD/DEBIAN/control" << EOF
Package: $APP_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Installed-Size: $INSTALLED_SIZE
Maintainer: $MAINTAINER
Homepage: $HOMEPAGE
Depends: python3, python3-tk, systemd
Recommends: pkexec | policykit-1
Description: Agendador de desligamento com interface gráfica
 Programe o desligamento do computador por atalhos rápidos (30 min, 1h, 2h,
 4h) ou por horário específico, com contador regressivo e cancelamento.
 Usa o systemd-logind e solicita autenticação (polkit) quando necessário.
EOF

# Construção (arquivos pertencem a root:root dentro do pacote)
dpkg-deb --root-owner-group --build "$BUILD" "$OUT" >/dev/null

echo
echo "=========================================="
echo "Pacote criado com sucesso!"
echo "$OUT"
echo
echo "Instale usando:"
echo "sudo apt install ./$OUT"
echo "=========================================="
