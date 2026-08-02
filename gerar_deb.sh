#!/bin/bash
set -e

APP_NAME="desligamento-inteligente"
VERSION="1.0"
BUILD="pkg_build"

MAIN_SCRIPT="desligamento.py"
ICON="icon.png"

echo "==> Gerando pacote .deb..."

# Limpeza
rm -rf "$BUILD"
mkdir -p "$BUILD"/DEBIAN
mkdir -p "$BUILD/usr/bin"
mkdir -p "$BUILD/usr/share/$APP_NAME"
mkdir -p "$BUILD/usr/share/applications"
mkdir -p "$BUILD/usr/share/icons/hicolor/256x256/apps"

# Copiar programa
cp "$MAIN_SCRIPT" "$BUILD/usr/share/$APP_NAME/"
chmod 755 "$BUILD/usr/share/$APP_NAME/$MAIN_SCRIPT"

# Launcher
cat > "$BUILD/usr/bin/$APP_NAME" << EOF
#!/bin/bash
exec python3 /usr/share/$APP_NAME/$MAIN_SCRIPT "\$@"
EOF

chmod 755 "$BUILD/usr/bin/$APP_NAME"

# Ícone
cp "$ICON" "$BUILD/usr/share/$APP_NAME/icon.png"
cp "$ICON" "$BUILD/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png"

# Desktop
cat > "$BUILD/usr/share/applications/$APP_NAME.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Desligamento Inteligente
Comment=Agendador de desligamento profissional
Exec=$APP_NAME
Icon=$APP_NAME
Terminal=false
Categories=System;Utility;
StartupNotify=true
EOF

# Control
cat > "$BUILD/DEBIAN/control" << EOF
Package: $APP_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Maintainer: Jackson Quequi
Depends: python3 (>=3.10), python3-tk, systemd
Description: Aplicativo profissional para agendamento de desligamento.
 Interface gráfica em Tkinter com persistência de agendamentos.
EOF

# Permissões
chmod 755 "$BUILD/DEBIAN"

# Construção
dpkg-deb --build "$BUILD"

mv "${BUILD}.deb" "${APP_NAME}_${VERSION}_all.deb"

rm -rf "$BUILD"

echo
echo "=========================================="
echo "Pacote criado com sucesso!"
echo "${APP_NAME}_${VERSION}_all.deb"
echo
echo "Instale usando:"
echo "sudo apt install ./${APP_NAME}_${VERSION}_all.deb"
echo "=========================================="