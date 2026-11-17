import {BrowserRouter,Routes,Route} from 'react-router-dom';import {useAuth} from '../stores/auth';import {ResearchProvider} from '../stores/research';import {Layout} from '../components/Layout';import {Login} from '../pages/Login';import {Overview} from '../pages/Overview';import {Inputs} from '../pages/Inputs';import {Configure} from '../pages/Configure';import {Results} from '../pages/Results';import {Notes} from '../pages/Notes';import {Audit} from '../pages/Audit';import {Privacy} from '../pages/Privacy';import {SharedRelease} from '../pages/SharedRelease';
export function Router(){
    const {user}=useAuth();
    const shared=<Route path="/shared/releases/:token" element={<SharedRelease/>}/>;
    if(!user)return <BrowserRouter><Routes>{shared}<Route path="*" element={<Login/>}/></Routes></BrowserRouter>;
    return <BrowserRouter><ResearchProvider><Routes>{shared}<Route element={<Layout/>}><Route path="/" element={<Overview/>}/><Route path="/inputs" element={<Inputs/>}/><Route path="/configure" element={<Configure/>}/><Route path="/results" element={<Results/>}/><Route path="/notes" element={<Notes/>}/><Route path="/audit" element={<Audit/>}/><Route path="/privacy" element={<Privacy/>}/><Route path="*" element={<Overview/>}/></Route></Routes></ResearchProvider></BrowserRouter>;
}
