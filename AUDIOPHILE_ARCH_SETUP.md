# Audiophile Arch Linux Setup Guide

Complete setup for headless audiophile Arch Linux with RT kernel optimizations.

## Prerequisites
- New PC with NVMe drive
- USB stick for installation media
- Ethernet connection

## 1. Create Installation Media
**On any computer:**
- Download Arch ISO from https://archlinux.org/download/
- Flash to USB: `dd if=archlinux.iso of=/dev/sdX bs=4M status=progress`

## 2. Boot and Install Base System
**Boot from USB:**

```bash
# Verify ethernet connection
ping archlinux.org

# Partition NVMe drive (512MB EFI + 64GB root)
parted --script /dev/nvme0n1 mklabel gpt \
  mkpart primary fat32 1MiB 513MiB \
  mkpart primary ext4 513MiB 64.5GiB \
  set 1 esp on

# Format partitions
mkfs.fat -F32 /dev/nvme0n1p1
mkfs.ext4 /dev/nvme0n1p2

# Mount filesystems
mount /dev/nvme0n1p2 /mnt
mkdir /mnt/boot
mount /dev/nvme0n1p1 /mnt/boot

# Install base system
pacstrap /mnt base linux linux-firmware base-devel

# Generate fstab
genfstab -U /mnt >> /mnt/etc/fstab

# Enter chroot
arch-chroot /mnt
```

## 3. Basic System Configuration

```bash
# Set timezone (Dublin, Ireland)
ln -sf /usr/share/zoneinfo/Europe/Dublin /etc/localtime
hwclock --systohc

# Configure locale
echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen
locale-gen
echo "LANG=en_US.UTF-8" > /etc/locale.conf

# Set hostname
echo "audiophile" > /etc/hostname

# Set root password
passwd

# Install bootloader, vim, and SSH
pacman -S grub efibootmgr vim openssh
grub-install --target=x86_64-efi --efi-directory=/boot
grub-mkconfig -o /boot/grub/grub.cfg

# Configure network
pacman -S dhcpcd
systemctl enable dhcpcd

# Enable SSH server
systemctl enable sshd

# Create user (replace 'username' with desired name)
useradd -m -G wheel,audio -s /bin/bash username
passwd username

# Enable sudo
EDITOR=vim visudo
# Uncomment: %wheel ALL=(ALL:ALL) ALL

# Exit and reboot
exit
reboot
```

## 4. Install RT Kernel and Audio Optimizations
**After reboot, login as user:**

```bash
# Install AUR helper
sudo pacman -S git
git clone https://aur.archlinux.org/yay.git
cd yay
makepkg -si
cd .. && rm -rf yay

# Install RT kernel
yay -S linux-rt linux-rt-headers

# Configure GRUB for audiophile optimizations
sudo vim /etc/default/grub
# Change line to:
# GRUB_CMDLINE_LINUX_DEFAULT="threadirqs isolcpus=2,3 rcu_nocbs=2,3 nohz_full=2,3"

sudo grub-mkconfig -o /boot/grub/grub.cfg
```

## 5. Audio System Setup

```bash
# Install headless audio stack
sudo pacman -S pipewire pipewire-alsa pipewire-pulse pipewire-jack wireplumber alsa-utils

# Configure audio limits
sudo vim /etc/security/limits.conf
# Add these lines:
# @audio - rtprio 95
# @audio - memlock unlimited

# Reboot to RT kernel
sudo reboot
```

## 6. Final Verification
**Select RT kernel from GRUB menu, then:**

```bash
# Verify RT kernel
uname -r  # Should show "rt"

# Test real-time scheduling
chrt -f 50 echo "RT working"  # Should work without error
```

## 7. Optional Audio Software

```bash
# Music Player Daemon
sudo pacman -S mpd ncmpcpp

# Mopidy (for TIDAL integration)
yay -S mopidy

# Audio tools
sudo pacman -S sox ffmpeg

# List audio devices
aplay -l
```

## System Specifications
- **Kernel**: RT kernel with low-latency optimizations
- **Audio**: PipeWire with JACK compatibility
- **Interface**: Headless (CLI only)
- **Network**: Ethernet with SSH access
- **Storage**: 64GB root partition on NVMe

## Key Optimizations
- Real-time kernel preemption
- CPU isolation for audio processing
- High-priority audio group privileges
- Minimal system overhead (no GUI)
- Optimized kernel parameters for audio latency

## Notes
- Replace `username` with your desired username
- Adjust timezone if not in Dublin, Ireland
- RT kernel provides sub-millisecond audio latency
- System is optimized for professional audio work