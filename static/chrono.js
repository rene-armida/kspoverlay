import { defineComponent } from 'vue'

export default defineComponent({
    props: {
        met: {type: String, required: true},
        igt: {type: String, required: true}
    },
    template: `
        <div id="chrono">
            <span id="missionET">T+{{ met }}</span>
            <span id="date">{{ igt }}</span>
        </div>`
})
