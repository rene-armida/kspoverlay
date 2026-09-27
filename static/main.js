import { createApp, defineComponent } from 'vue';
import Chrono from '/static/chrono.js';

/* 
'display' modes
nodata - startup, don't know what to show yet
flight - orbital
flightPause - ESC menu active, hide it
launch - small game + charts
launchPause - ESC menu active during launch
*/

const FlightDisplay = defineComponent({
    template: ``
})

function mountApp() {
    const refreshIntervalMs = 5000;

    createApp({
        data() {
            return {
                display: 'nodata',
                missionName: '',
                currentTime: '',
                missionElapsedTime: '',
                prevStage: '',
                currentStage: '',
                nextStage: '',
            }
        },
        methods: {
            async update() {
                try {
                    const resp = await fetch("/update/_latest");
                    const data = (await resp.json())
                    this.display = data.display;
                    this.missionName = data.missionName;
                    this.currentTime = data.inGameTime;
                    this.missionElapsedTime = data.missionElapsedTime;
                } catch (error) {
                    console.log('Error! Could not reach the backend');
                }

                if ( this.display == "nodata" ) {
                    
                }
            }
        },
        mounted() {
            setInterval(this.update, refreshIntervalMs);
        }
    })
    .component("Chrono", Chrono)
    .component("FlightDisplay", FlightDisplay)
    .mount("#main");
}

export default {
    "mountApp": mountApp
}
