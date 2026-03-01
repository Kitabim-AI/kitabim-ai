#!/bin/bash
# One-time VM provisioning script for Kitabim AI on GCE
# Run after SSH-ing into the VM: bash setup-vm.sh YOUR_DOMAIN YOUR_EMAIL
# Example: bash setup-vm.sh kitabim.ai admin@kitabim.ai
set -euo pipefail

DOMAIN="${1:-kitabim.ai}"
EMAIL="${2:-admin@kitabim.ai}"
APP_DIR="/opt/kitabim"
DATA_DISK="/dev/sdb"
DATA_MOUNT="/mnt/kitabim-data"
REGION="us-south1"

echo "==> [1/7] System packages"
sudo apt-get update -q
sudo apt-get install -y -q \
    ca-certificates curl gnupg lsb-release \
    git certbot postgresql-client \
    htop vim

echo "==> [2/7] Docker"
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
sudo apt-get install -y -q docker-compose-plugin
echo "Docker installed. NOTE: log out and back in for group membership to take effect."
echo "For now, using sudo docker commands..."

echo "==> [3/7] Mount persistent data disk ($DATA_DISK → $DATA_MOUNT)"
if ! sudo blkid "$DATA_DISK" &>/dev/null; then
    echo "Formatting $DATA_DISK..."
    sudo mkfs.ext4 -F "$DATA_DISK"
fi
sudo mkdir -p "$DATA_MOUNT"
if ! grep -q "$DATA_DISK" /etc/fstab; then
    echo "$DATA_DISK $DATA_MOUNT ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab
fi
sudo mount -a
sudo mkdir -p "$DATA_MOUNT/uploads" "$DATA_MOUNT/covers"
sudo chmod 777 "$DATA_MOUNT"
echo "Persistent disk mounted at $DATA_MOUNT"

echo "==> [4/7] App directory"
sudo mkdir -p "$APP_DIR"
sudo chown "$USER:$USER" "$APP_DIR"

echo ""
echo "ACTION REQUIRED: Clone your repo to $APP_DIR"
echo "  git clone https://github.com/YOUR_ORG/kitabim-ai.git $APP_DIR"
echo "  (or use a deploy key / personal access token)"
echo ""
read -p "Press Enter once the repo is cloned to $APP_DIR..."

echo "==> [5/7] GCS service account key"
sudo mkdir -p /etc/gcs
echo ""
echo "ACTION REQUIRED: Copy gcs-key.json to the VM"
echo "  From your local machine, run:"
echo "  gcloud compute scp /path/to/gcs-key.json \$(hostname):/tmp/gcs-key.json --zone=us-south1-c"
echo "  Then here: sudo mv /tmp/gcs-key.json /etc/gcs/key.json && sudo chmod 400 /etc/gcs/key.json"
echo ""
read -p "Press Enter once /etc/gcs/key.json is in place..."

echo "==> [6/7] SSL certificate (Let's Encrypt)"
echo "Stopping any existing web server on port 80..."
sudo systemctl stop nginx 2>/dev/null || true

sudo certbot certonly --standalone \
    -d "$DOMAIN" -d "www.$DOMAIN" \
    --non-interactive --agree-tos \
    -m "$EMAIL"

# Auto-renew cron (reload nginx container after renewal)
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'docker compose -f $APP_DIR/deploy/gcp/docker-compose.yml exec nginx nginx -s reload'") | crontab -
echo "SSL cert issued and auto-renewal configured."

echo "==> [7/7] Artifact Registry auth"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo ""
echo "============================================"
echo " Setup complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Copy deploy/gcp/.env.template to $APP_DIR/deploy/gcp/.env and fill in secrets"
echo "  2. Run the deploy script from your local machine:"
echo "     ./deploy/gcp/scripts/deploy.sh"
echo ""
echo "  Reminder: set DATABASE_URL in .env to:"
echo "    postgresql://kitabim:PASSWORD@10.158.0.5:5432/kitabim-ai"
