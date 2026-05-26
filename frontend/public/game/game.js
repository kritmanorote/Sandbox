const WIDTH = 800;
const HEIGHT = 400;
const GROUND_Y = 340;

class GameScene extends Phaser.Scene {
    constructor() {
        super({ key: 'GameScene' });
    }

    create() {
        // Starfield background
        for (let i = 0; i < 70; i++) {
            const x = Phaser.Math.Between(0, WIDTH);
            const y = Phaser.Math.Between(0, GROUND_Y - 10);
            const r = Phaser.Math.FloatBetween(0.8, 2.2);
            this.add.circle(x, y, r, 0xffffff).setAlpha(Phaser.Math.FloatBetween(0.2, 0.7));
        }

        // Ground bar + glow
        this.add.rectangle(WIDTH / 2, GROUND_Y + 6, WIDTH, 10, 0x00ffff, 0.12);
        this.add.rectangle(WIDTH / 2, GROUND_Y + 2, WIDTH, 4, 0x00ffff);

        // Player
        this.PW = 36;
        this.PH = 50;
        this.player = this.add.rectangle(
            120,
            GROUND_Y - this.PH / 2,
            this.PW,
            this.PH,
            0x00ffff
        ).setStrokeStyle(2, 0x88ffff);

        this.velY = 0;
        this.onGround = true;
        this.GRAVITY = 1400;
        this.JUMP_VEL = -650;

        // Obstacles array
        this.obstacles = [];
        this.spawnTimer = 0;
        this.nextSpawn = 1200;

        // Game state
        this.baseSpeed = 280;
        this.speed = this.baseSpeed;
        this.elapsed = 0;
        this.score = 0;
        this.dead = false;

        // HUD
        this.scoreText = this.add.text(WIDTH - 16, 16, 'SCORE: 0', {
            fontSize: '18px',
            color: '#00ffff',
            fontFamily: 'monospace'
        }).setOrigin(1, 0);

        this.speedText = this.add.text(16, 16, 'SPEED: 1.0x', {
            fontSize: '16px',
            color: '#ff6699',
            fontFamily: 'monospace'
        }).setOrigin(0, 0);

        this.add.text(WIDTH / 2, 14, 'SPACE / TAP to jump', {
            fontSize: '13px',
            color: '#ffffff',
            fontFamily: 'monospace'
        }).setOrigin(0.5, 0).setAlpha(0.35);

        // Input
        this.cursors = this.input.keyboard.createCursorKeys();
        this.spaceKey = this.input.keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.SPACE);
        this.wKey = this.input.keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.W);
        this.input.on('pointerdown', () => this.doJump());
    }

    doJump() {
        if (this.onGround && !this.dead) {
            this.velY = this.JUMP_VEL;
            this.onGround = false;
        }
    }

    update(time, delta) {
        if (this.dead) return;

        const dt = delta / 1000;
        this.elapsed += dt;

        // Speed increases every 5 s by 30 px/s
        this.speed = this.baseSpeed + Math.floor(this.elapsed / 5) * 30;

        // Score
        this.score = Math.floor(this.elapsed * 10);
        this.scoreText.setText('SCORE: ' + this.score);
        this.speedText.setText('SPEED: ' + (this.speed / this.baseSpeed).toFixed(1) + 'x');

        // Jump input
        if (
            Phaser.Input.Keyboard.JustDown(this.cursors.up) ||
            this.spaceKey.isDown ||
            Phaser.Input.Keyboard.JustDown(this.wKey)
        ) {
            this.doJump();
        }

        // Player physics
        this.velY += this.GRAVITY * dt;
        this.player.y += this.velY * dt;

        const groundLevel = GROUND_Y - this.PH / 2;
        if (this.player.y >= groundLevel) {
            this.player.y = groundLevel;
            this.velY = 0;
            this.onGround = true;
        }

        // Neon pulse
        this.player.setAlpha(0.82 + Math.sin(time / 140) * 0.18);

        // Obstacle spawning
        this.spawnTimer += delta;
        if (this.spawnTimer >= this.nextSpawn) {
            this.spawnTimer = 0;
            this.nextSpawn = Phaser.Math.Between(650, 1700);
            this.spawnObstacle();
        }

        // Move obstacles + collision
        for (let i = this.obstacles.length - 1; i >= 0; i--) {
            const obs = this.obstacles[i];
            obs.x -= this.speed * dt;

            if (obs.x < -obs.width) {
                obs.destroy();
                this.obstacles.splice(i, 1);
                continue;
            }

            if (this.hits(this.player, obs)) {
                this.triggerGameOver();
                return;
            }
        }
    }

    spawnObstacle() {
        const h = Phaser.Math.Between(28, 82);
        const w = Phaser.Math.Between(16, 40);
        const obs = this.add.triangle(
            WIDTH + w / 2,
            GROUND_Y - h / 2,
            0, h,
            w, h,
            w / 2, 0,
            0xff0066
        ).setStrokeStyle(2, 0xff88bb);
        this.obstacles.push(obs);
    }

    hits(a, b) {
        const m = 5; // shrink hitbox slightly for fairness
        return !(
            a.x + a.width / 2 - m < b.x - b.width / 2 ||
            a.x - a.width / 2 + m > b.x + b.width / 2 ||
            a.y + a.height / 2 - m < b.y - b.height / 2 ||
            a.y - a.height / 2 + m > b.y + b.height / 2
        );
    }

    triggerGameOver() {
        this.dead = true;
        this.player.setFillStyle(0xff0066).setAlpha(1);

        const params = new URLSearchParams(window.location.search);
        const API_URL = params.get('api') || 'http://localhost:8000';

        this.add.rectangle(WIDTH / 2, HEIGHT / 2, WIDTH, HEIGHT, 0x000000, 0.78);

        this.add.text(WIDTH / 2, HEIGHT / 2 - 95, 'GAME OVER', {
            fontSize: '54px', color: '#ff0066', fontFamily: 'monospace',
            fontStyle: 'bold', stroke: '#ff0066', strokeThickness: 1
        }).setOrigin(0.5);

        this.add.text(WIDTH / 2, HEIGHT / 2 - 38, 'SCORE: ' + this.score, {
            fontSize: '30px', color: '#00ffff', fontFamily: 'monospace'
        }).setOrigin(0.5);

        // DOM name input
        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = 'Enter your name';
        input.maxLength = 32;
        Object.assign(input.style, {
            position: 'absolute', left: '50%', top: '54%',
            transform: 'translateX(-50%)',
            background: '#0a0a1a', color: '#00ffff',
            border: '2px solid #00ffff', padding: '8px 14px',
            fontFamily: 'monospace', fontSize: '16px',
            outline: 'none', textAlign: 'center', width: '200px', zIndex: 10
        });
        document.body.appendChild(input);
        input.focus();

        const statusText = this.add.text(WIDTH / 2, HEIGHT / 2 + 42, '', {
            fontSize: '13px', color: '#aaaaaa', fontFamily: 'monospace'
        }).setOrigin(0.5);

        const submitScore = async (name) => {
            if (!name.trim()) return;
            input.disabled = true;
            statusText.setText('Submitting...');
            try {
                await fetch(`${API_URL}/leaderboard`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name.trim(), score: this.score })
                });
                const res = await fetch(`${API_URL}/leaderboard`);
                const top = await res.json();
                input.remove();
                this.showLeaderboard(top);
            } catch (e) {
                statusText.setText('Could not save score.');
                input.remove();
                this.showRestartBtn();
            }
        };

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') submitScore(input.value);
        });

        const btn = this.add.rectangle(WIDTH / 2, HEIGHT / 2 + 68, 160, 40, 0x00ffff)
            .setStrokeStyle(2, 0xffffff).setInteractive();
        this.add.text(WIDTH / 2, HEIGHT / 2 + 68, '[ SUBMIT ]', {
            fontSize: '16px', color: '#0a0a1a', fontFamily: 'monospace', fontStyle: 'bold'
        }).setOrigin(0.5);
        btn.on('pointerover', () => btn.setFillStyle(0x00dddd));
        btn.on('pointerout', () => btn.setFillStyle(0x00ffff));
        btn.on('pointerdown', () => submitScore(input.value));
    }

    showLeaderboard(top) {
        this.add.text(WIDTH / 2, HEIGHT / 2 - 38, 'TOP SCORES', {
            fontSize: '20px', color: '#ff6699', fontFamily: 'monospace', fontStyle: 'bold'
        }).setOrigin(0.5);

        top.forEach((entry, i) => {
            const y = HEIGHT / 2 - 12 + i * 22;
            this.add.text(WIDTH / 2, y,
                `${String(i + 1).padStart(2)}. ${entry.name.padEnd(14)} ${entry.score}`, {
                fontSize: '14px', color: i === 0 ? '#ffff00' : '#00ffff', fontFamily: 'monospace'
            }).setOrigin(0.5);
        });

        this.showRestartBtn();
    }

    showRestartBtn() {
        const btn = this.add.rectangle(WIDTH / 2, HEIGHT - 44, 200, 42, 0x00ffff)
            .setStrokeStyle(2, 0xffffff).setInteractive();
        this.add.text(WIDTH / 2, HEIGHT - 44, '[ PLAY AGAIN ]', {
            fontSize: '16px', color: '#0a0a1a', fontFamily: 'monospace', fontStyle: 'bold'
        }).setOrigin(0.5);
        btn.on('pointerover', () => btn.setFillStyle(0x00dddd));
        btn.on('pointerout', () => btn.setFillStyle(0x00ffff));
        btn.on('pointerdown', () => this.scene.restart());
        this.input.keyboard.once('keydown-SPACE', () => this.scene.restart());
        this.input.keyboard.once('keydown-ENTER', () => this.scene.restart());
    }
}

new Phaser.Game({
    type: Phaser.AUTO,
    width: WIDTH,
    height: HEIGHT,
    backgroundColor: '#0a0a1a',
    scene: GameScene,
    scale: {
        mode: Phaser.Scale.FIT,
        autoCenter: Phaser.Scale.CENTER_BOTH
    }
});
