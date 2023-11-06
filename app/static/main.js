var chart = new Chart(document.getElementById('statsCanvas'), {
    type: 'line',
    data: { 
        datasets: []
    },
    options: {
        tension: .4,
        spanGaps: true,
        scales: {
            x: {
                type: 'time',
            }
        }
    }
});

initialize();
document.getElementById("clusterCheckbox").onclick = async () => await onScopeChange()
document.getElementById("neighbourhoodCheckbox").onclick = async () => await onScopeChange()
document.getElementById("updateDataButton").onclick = async () => await renewData()
document.getElementById("dgCheckbox").onclick = async () => await onConfigChange()
document.getElementById("ccCheckbox").onclick = async () => await onConfigChange()
document.getElementById("jyCheckbox").onclick = async () => await onConfigChange()
document.getElementById("scCheckbox").onclick = async () => await onConfigChange()
document.getElementById("numActivityCheckbox").onclick = async () => await onConfigChange()
document.getElementById("numParticipantCheckbox").onclick = async () => await onConfigChange()

function uri(endpoint) {
    // get an API URI for the given endpoint
    return `${location.protocol}//${location.host}/${endpoint}`
}

function genConfig() {
    // generate a bit string representing the state of config values (not including area selection).
    var config = 0n
    ;["activityCheckbox", "typeRadio", "scopeRadio"].forEach((name) => {
        Array.from(document.querySelectorAll(`input[name=${name}]`), (el) => {
            config <<= 1n
            config |= BigInt(el.checked)
        })
    })
    return `${config}`
}

function genAreaConfig() {
    // generate a bit string representing the state of the area selection checkboxes
    var config = 0n
    Array.from(document.querySelectorAll(`input[name=areaCheckbox]`), (el) => {
        config <<= 1n
        config |= BigInt(el.checked)
    })
    return `${config}`
}

function loadConfig(config) {
    // given a bit field string, reproduce the config it was generated from.  This is the inverse of the genConfig
    // function, so the order of operations needs to be precisely reversed.
    config = BigInt(config)
    ;["scopeRadio", "typeRadio", "activityCheckbox"].forEach((name) => {
        var checkboxes = Array.from(document.querySelectorAll(`input[name=${name}]`)).reverse()
        checkboxes.forEach((el) => {
            el.checked = ((config & 1n) != 0n)
            config >>= 1n
        })
    })
}

async function loadAreaConfig(config) {
    // given a bit field string, reproduce the area selection it was generated from.  This is the inverse of the
    // genAreaConfig function, so the order of operations needs to be precisely reversed.
    config = BigInt(config)
    var checkboxes = Array.from(document.querySelectorAll(`input[name=areaCheckbox]`)).reverse()
    checkboxes.forEach((el) => {
        el.checked = ((config & 1n) != 0n)
        config >>= 1n
    })

}

function findConfig() {
    // Look for a config value in the URL search params and then in a cookie.  If neither is available, then
    // a default config is loaded.
    const params = new URLSearchParams(window.location.search);
    if (params.has('c')) {
        // config was passed in as a GET param
        return params.get('c')
    }
    else {
        c = getCookie("config")
        if (c) {
            return c
        }
        // load a default config if there's no cookie or GET param
        document.getElementsByName("activityCheckbox").forEach((el) => el.checked = true)
        document.getElementById("numActivityCheckbox").checked = true
        document.getElementById("clusterCheckbox").checked = true
        return genConfig()
    }
}

function findAreaConfig() {
    // Look for a area selection config value in the URL search params and then in cookies.  If neither is available,
    // then a default config is loaded.  Two cookies are searched, one if clusters are loaded and the other if
    // neighbourhoods are loaded.
    const params = new URLSearchParams(window.location.search);
    if (params.has('a')) {
        // config was passed in as a GET param
        return params.get('a')
    }
    else {
        let a
        if (document.getElementById("clusterCheckbox").checked) {
            a = getCookie("clusterAreas")
        }
        else if (document.getElementById("neighbourhoodCheckbox").checked) {
            a = getCookie("nbhdAreas")
        }
        if (a) {
            return a
        }
        // load a default config if there's no cookie or GET param
        document.getElementById("area9Checkbox").checked = true
        return genAreaConfig()
    }
}

async function initialize() {
    // query the API for a mapping of clusters to neighbourhoods, and then build checkbox selectors
    // for each neighbourhood, load config data, and generate the initial chart
    loadConfig(findConfig())
    if (document.getElementById("clusterCheckbox").checked) {
        await buildAreaCheckboxes('cluster')
    }
    else if (document.getElementById("neighbourhoodCheckbox").checked) {
        await buildAreaCheckboxes('neighbourhood')
    }
    else {
        console.error("Scope not selected.")
    }
    
    await loadAreaConfig(findAreaConfig())
    await refreshChart()
}

function appendAreaCheckbox(areaList, i, value, text) {
    // Build an element representing an area selection checkbox and add it to the given areaList element
    // Args:
    //     i: unique identifier for this checkbox, used to name the checkbox.
    //     value: the string that will be returned when accessing the input's element's value
    //     text: the text to put in the checkbox's label
    let div = document.createElement('div')
    div.className = 'form-check'
    let input = document.createElement('input')
    input.className = 'form-check-input'
    input.type = 'checkbox'
    input.value = value
    input.id = `area${i}Checkbox`
    input.name = 'areaCheckbox'
    input.onclick = async () => await onAreaChange()
    let label = document.createElement('label')
    label.className = 'form-check-label'
    label.setAttribute('for', `area${i}Checkbox`)
    label.innerText = text
    div.appendChild(input)
    div.appendChild(label)
    areaList.appendChild(div)
}

async function buildAreaCheckboxes(area_type) {
    // Given the configured scope (cluster or neighbourhood), retrieve a list of areas in that scope, empty out the
    // areaList div, and re-build the list of checkboxes based on the list provided by the API.
    await fetch(uri(`list/${area_type}`), {
        method: "GET"
    }).then((response => response.json()))
      .then((json) => {
        var i = 0;
        areaList = document.getElementById('areaList')
        areaTitle = document.getElementById('areaTitle')
        areaList.innerHTML = ""
        areaList.appendChild(areaTitle)
        Object.entries(json).sort().forEach(([clusterGroup, clusterData]) => {
            // todo: do something with cluster group
            if (area_type == "neighbourhood") {
                areaTitle.innerText = "Neighbourhoods"
                // clusterData is a mapping of cluster name to a sequence of neighbourhoods
                Object.entries(clusterData).sort().forEach(([cluster, nbhds]) => {
                    nbhds.sort().forEach((nbhd) => {
                        appendAreaCheckbox(areaList, i, nbhd, `${nbhd} (${cluster})`)
                        i++
                    })
                })
            }
            else if (area_type == "cluster") {
                areaTitle.innerText = "Clusters"
                // clusterData is a sequence of clusters in the current cluster group
                clusterData.sort().forEach((cluster) => {
                    appendAreaCheckbox(areaList, i, cluster, cluster)
                    i++
                })
            }
            else {
                console.error("Area type invalid while building checkboxes.")
            }
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

async function onAreaChange() {
    // event handler for when an area selection checkbox is checked or unchecked.  Updates cookies and refreshes
    // the chart.
    if (document.getElementById("clusterCheckbox").checked) {
        setCookie("clusterAreas", genAreaConfig(), 365)
    }
    else if (document.getElementById("neighbourhoodCheckbox").checked) {
        setCookie("nbhdAreas", genAreaConfig(), 365)
    }
    await refreshChart()
}

async function onConfigChange() {
    // event handler for when a config value changes.  Updates config cookie and refreshes the chart.
    setCookie('config', genConfig(), 365)
    await refreshChart()
}

async function onScopeChange() {
    // event handler for when the scope setting changes.  Rebuilds the area selection list and then triggers the
    // onConfigChange handler.
    if (document.getElementById("clusterCheckbox").checked) {
        await buildAreaCheckboxes('cluster')
        await loadAreaConfig(getCookie("clusterAreas"))
    }
    else if (document.getElementById("neighbourhoodCheckbox").checked) {
        await buildAreaCheckboxes('neighbourhood')
        await loadAreaConfig(getCookie("nbhdAreas"))
    }
    await onConfigChange();
}

function copyLink() {
    button = document.getElementById("copyLinkButton")
    navigator.clipboard.writeText(uri(`?c=${genConfig()}&a=${genAreaConfig()}`))
    button.disabled = true;
    button.innerText = "Copied!"
    // revert button text to "Copy Link" after 1 second
    new Promise(() => setTimeout(() => {
        button.innerText = "Copy Link"
        button.disabled = false
    }, 1000))
}

async function renewData() {
    // ask the API to invalidate its data cache and reload data from the source spreadsheet.  This disables
    // the update button and runs a spinner until the API replies (which can take several seconds)
    button = document.getElementById("updateDataButton")
    button.disabled = true;
    button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span>&nbsp;Loading...'
    await fetch(uri('stats'), {method: "DELETE"})
    .then(() => {
        button.disabled = false
        button.innerText = "Update Data"
    })
    await refreshChart()
}

async function refreshChart() {
    // get the stats for the checked neighbourhoods and set the chart data to the result
    let scope;
    if (document.getElementById("clusterCheckbox").checked) {
        scope = "Cluster"
    }
    else if (document.getElementById("neighbourhoodCheckbox").checked) {
        scope = "Neighbourhood"
    }
    else {
        console.error("Scope not selected when refreshing chart.")
    }
    await fetch(uri('stats'), {
      method: "POST",
      body: JSON.stringify({
          names: Array.from(document.querySelectorAll('input[name=areaCheckbox]:checked'), (el) => el.value),
          scope: scope,
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