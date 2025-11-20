# DBB Team Logos

This directory contains SVG logos for German basketball teams in the DBB module.

## Automatic Logo Discovery

Logos are **automatically discovered** using substring matching between the logo filename and team names. You don't need to manually assign logos to teams - just name the files appropriately!

### How It Works

1. Place logo files (SVG, PNG, JPG) in this directory
2. Name them with a substring of the team name (lowercase, hyphen-separated)
3. Logos will be automatically matched to teams (both tracked teams and opponents)

### Examples

- `bierden-bassen.svg` → matches "BG Bierden-Bassen Achim"
- `tv-bremen.svg` → matches "TV Bremen" or "TV Bremen II"
- `werder.svg` → matches "SG Werder Bremen"

The system normalizes both filenames and team names (lowercase, handles umlauts, removes special characters) and checks if the filename is a substring of the team name.

## Manual Override

If needed, you can manually specify a logo filename in the TrackedTeam admin. Manual assignments take precedence over auto-discovery.

## Naming Conventions

**Recommended naming pattern:**
- Use lowercase letters
- Use hyphens instead of spaces
- Use recognizable team name fragments
- Example: `team-name.svg`

**Normalization rules:**
- German umlauts are converted (ä→ae, ö→oe, ü→ue, ß→ss)
- Special characters are removed
- Spaces and hyphens are preserved during matching

## Format Guidelines

- **Format**: SVG (preferred), PNG, JPG, or JPEG
- **Size**: Logos should be square or close to square aspect ratio
- **Quality**: Use vector graphics (SVG) when possible for best scaling

## Fallback

If no logo is found for a team, the card will display the first two letters of the team name as a placeholder.

