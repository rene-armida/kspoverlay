import { createApp } from 'vue';
import Chrono from '/static/chrono.js';

function mountApp() {
    createApp({
        data() {
            return {
                missionName: 'Lond III',
                currentTime: 'Y450 D130',
                missionElapsedTime: 'T+ 101Y 358D',
                prevStage: "Refuel Freighter",
                currentStage: "Ejection Burn",
                nextStage: "Correction Burn(s)",
                intervalId: NaN
            }
        },
        methods: {
            async update() {
                try {
                    const resp = await fetch("/update/_latest");
                    const data = (await resp.json())
                    this.missionName = data.missionName;
                    this.currentTime = data.inGameTime;
                    this.missionElapsedTime = data.missionElapsedTime;
                } catch (error) {
                    console.log('Error! Could not reach the backend');
                }
            }
        },
        mounted() {
            this.intervalId = setInterval(this.update, 500);
            console.log("refresh interval id" + this.intervalId)
        }
    })
    .component("Chrono", Chrono)
    .mount("#main");
}

export default {
    "mountApp": mountApp
}
