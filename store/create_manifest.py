"""Create Store package metadata with the identity supplied by Partner Center."""
import argparse
import json
from pathlib import Path
import re
from xml.sax.saxutils import escape, quoteattr
from PIL import Image

p = argparse.ArgumentParser()
p.add_argument('--package-dir', required=True, type=Path)
p.add_argument('--identity', required=True)
p.add_argument('--publisher', required=True)
p.add_argument('--publisher-display', required=True)
p.add_argument('--version', required=True)
p.add_argument('--icon', required=True, type=Path)
a = p.parse_args()
root_dir = Path(__file__).resolve().parent.parent
packs = json.loads((root_dir / 'application' / 'locales' / 'ui_packs.json').read_text(encoding='utf-8'))
languages = sorted({'fr', *(pack['html_lang'] for pack in packs.values())})
resources = ''.join('<Resource Language=' + quoteattr(language) + ' />' for language in languages)
if not re.fullmatch(r'[A-Za-z0-9.-]{3,50}', a.identity):
    p.error('Invalid package identity')
parts = a.version.split('.')
if len(parts) != 4 or any(not x.isdigit() or int(x) > 65535 for x in parts) or parts[-1] != '0':
    p.error('Store version must contain four numbers, with revision 0')
if not a.publisher.startswith('CN='):
    p.error('Publisher must be the exact Partner Center publisher subject')
assets = a.package_dir / 'Assets'
assets.mkdir(parents=True, exist_ok=True)
with Image.open(a.icon) as icon:
    icon = icon.convert('RGBA')
    for name, size in [('StoreLogo.png', 50), ('Square44x44Logo.png', 44), ('Square150x150Logo.png', 150)]:
        icon.resize((size, size), Image.Resampling.LANCZOS).save(assets / name)
manifest = '''<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
 xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
 xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
 IgnorableNamespaces="uap rescap">
 <Identity Name={identity} Publisher={publisher} Version={version} ProcessorArchitecture="x64" />
 <Properties><DisplayName>Elden Ring PvP Tracker</DisplayName><PublisherDisplayName>{display}</PublisherDisplayName><Logo>Assets\\StoreLogo.png</Logo></Properties>
 <Dependencies><TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" /></Dependencies>
 <Resources>{resources}</Resources>
 <Applications><Application Id="Tracker" Executable="EldenRingTracker.exe" EntryPoint="Windows.FullTrustApplication">
 <uap:VisualElements DisplayName="Elden Ring PvP Tracker" Description="Elden Ring PvP Tracker" BackgroundColor="transparent" Square150x150Logo="Assets\\Square150x150Logo.png" Square44x44Logo="Assets\\Square44x44Logo.png" />
 </Application></Applications>
 <Capabilities><rescap:Capability Name="runFullTrust" /><Capability Name="internetClient" /></Capabilities>
</Package>
'''.format(identity=quoteattr(a.identity), publisher=quoteattr(a.publisher), version=quoteattr(a.version), display=escape(a.publisher_display), resources=resources)
(a.package_dir / 'AppxManifest.xml').write_text(manifest, encoding='utf-8')
