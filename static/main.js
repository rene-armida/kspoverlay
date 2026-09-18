import { createApp } from 'vue';

function mountFlightApp() {
    createApp({
        data() {
            return {
                missionName: 'Lond III',
                currentTime: 'Y450 D130',
                missionElapsedTime: 'T+ 101Y 358D',
                prevStage: "Refuel Freighter",
                currentStage: "Ejection Burn",
                nextStage: "Correction Burn(s)",
            }
        },
        methods: {
            async update() {
                try {
                    const resp = await fetch("/displaydata/flight");
                    this.missionName = (await resp.json()).missionName;
                } catch (error) {
                    console.log('Error! Could not reach the backend');
                }
            }
        },
        mounted() {
            setInterval(this.update, 500);
        }
    }).mount("#main");
}

export default {
    "flightApp": mountFlightApp,
}
