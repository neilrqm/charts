var chart = new Chart(document.getElementById('statsCanvas'), {
    type: 'line',
    data: { 
        datasets: []
    },
    options: {
        tension: .4,
        spanGaps: true,
    }
});

initialize();

function uri(endpoint) {
    // get an API URI for the given endpoint
    return `${location.protocol}//${location.host}/${endpoint}`
}

function genConfig() {
    // generate a bit string representing the state of cluster/nbhd checkboxes and other config values
    // There are several groups of config options, e.g. the group of checkboxes that select which areas
    // to include in the chart, the group of checkboxes that select which activities to chart, and the
    // radio button that selects whether to count activities or participants.  We iterate over each of
    // these groups, and then iterate over each part of the option group, to build a bit field representing
    // the state (e.g. selected or not-selected) of each element.  Then in the loadConfig function we do
    // the same thing in reverse order to read the bits back into the UI elements whose state they represent.
    var config = 0n
    ;["areaCheckbox", "activityCheckbox", "typeRadio"].forEach((name) => {
        Array.from(document.querySelectorAll(`input[name=${name}]`), (el) => {
            config <<= 1n
            config |= BigInt(el.checked)
        })
    })
    return `${config}`
}

function loadConfig(config) {
    // given a bit field string, reproduce the state it was generated from.  See genConfig for more info.
    config = BigInt(config)
    ;["typeRadio", "activityCheckbox", "areaCheckbox"].forEach((name) => {
        var checkboxes = Array.from(document.querySelectorAll(`input[name=${name}]`)).reverse()
        checkboxes.forEach((el) => {
            el.checked = ((config & 1n) != 0n)
            config >>= 1n
        })
    })
}

function initialize() {
    // query the API for a mapping of clusters to neighbourhoods, and then build checkbox selectors
    // for each neighbourhood, load config data, and generate the initial chart
    fetch(uri('stats/neighbourhood'), {
        method: "GET"
    }).then((response) => response.json())
      .then((json => buildAreaCheckboxes(json)))
      .then(() => {
        // try to load the config state
        const params = new URLSearchParams(window.location.search);
        if (params.has('c')) {
            // config was passed in as a GET param
            loadConfig(params.get('c'))
        }
        else {
            let c = getCookie("config")
            if (c) {
                // config was present as a cookie
                loadConfig(getCookie('config'))
            }
            else
            {
                // load a default config if there's no cookie or GET param
                document.getElementsByName("activityCheckbox").forEach((el) => el.checked = true)
                document.getElementById("numActivityCheckbox").checked = true
                document.getElementById("area9Checkbox").checked = true
            }
        }
      })
      .then(() => refreshChart())
}

function buildAreaCheckboxes(json) {
    var i = 0;
    areaList = document.getElementById('areaList')
    Object.entries(json).sort().forEach(([clusterGroup, clusterMap]) => {
        // todo: do something with cluster group
        Object.entries(clusterMap).sort().forEach(([cluster, nbhds]) => {
            nbhds.sort().forEach((nbhd) => {
                let div = document.createElement('div')
                div.className = 'form-check'
                let input = document.createElement('input')
                input.className = 'form-check-input'
                input.type = 'checkbox'
                input.value = nbhd
                input.id = `area${i}Checkbox`
                input.name = 'areaCheckbox'
                input.onclick = onStateChange
                let label = document.createElement('label')
                label.className = 'form-check-label'
                label.setAttribute('for', `area${i}Checkbox`)
                label.innerText = `${nbhd} (${cluster})`
                div.appendChild(input)
                div.appendChild(label)
                areaList.appendChild(div)
                i++
            })
        })

    })
}

function setCookie(cname, cvalue, exdays) {
    // from https://www.w3schools.com/js/js_cookies.asp
    // cname is cookie name, cvalue is cookie value, exdays is expiry time in days from now.
    const d = new Date();
    d.setTime(d.getTime() + (exdays*24*60*60*1000));
    let expires = "expires="+ d.toUTCString();
    document.cookie = cname + "=" + cvalue + ";" + expires + ";path=/";
}

function getCookie(cname) {
    // based on https://www.w3schools.com/js/js_cookies.asp
    let name = cname + "=";
    let decodedCookie = decodeURIComponent(document.cookie);
    let cookies = decodedCookie.split(';');
    for (let i = 0; i <cookies.length; i++) {
        let cookie = cookies[i].trim();
        if (cookie.indexOf(name) == 0) {
          return cookie.substring(name.length, cookie.length);
        }
      }
    return "";
}

function onStateChange() {
    var config = genConfig();
    setCookie('config', config, 365)
    refreshChart()
}

function copyLink() {
    button = document.getElementById("copyLinkButton")
    navigator.clipboard.writeText(uri(`?c=${genConfig()}`))
    button.disabled = true;
    button.innerText = "Copied!"
    new Promise(() => setTimeout(() => {
        button.innerText = "Copy Link"
        button.disabled = false
    }, 1000))
}

function renewData() {
    // ask the API to invalidate its data cache and reload data from the source spreadsheet.  This disables
    // the update button and runs a spinner until the API replies (which can take several seconds)
    button = document.getElementById("updateDataButton")
    button.disabled = true;
    button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span>Loading...'
    fetch(uri('stats/neighbourhood'), {method: "DELETE"})
    .then(() => {
        button.disabled = false
        button.innerText = "Update Data"
        refreshChart()
    })
}

function refreshChart() {
    // get the stats for the checked neighbourhoods and set the chart data to the result
    fetch(uri('stats/neighbourhood'), {
      method: "POST",
      body: JSON.stringify({
          names: Array.from(document.querySelectorAll('input[name=areaCheckbox]:checked'), (el) => el.value),
          activities: Array.from(document.querySelectorAll('input[name=activityCheckbox]:checked'), (el) => el.value),
          stats_type: Number(document.querySelector('input[name=typeRadio]:checked').value)
      }),
      headers: {
          "Content-type": "application/json; charset=UTF-8"
      }
    }).then((response) => response.json())
    .then((json) => {
          chart.data.datasets = Array.from(json, (el) => el.dataset)
          chart.update()
    });
}