import "axios";

declare module "axios" {
  export interface AxiosRequestConfig<D = unknown> {
    skipAuthRefresh?: boolean;
  }

  export interface InternalAxiosRequestConfig<D = unknown> {
    skipAuthRefresh?: boolean;
    _retry?: boolean;
  }
}
