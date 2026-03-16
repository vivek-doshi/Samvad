import { Pipe, PipeTransform } from '@angular/core';

@Pipe({
  name: 'markdown',
})
export class MarkdownPipe implements PipeTransform {

  transform(value: unknown, ...args: unknown[]): unknown {
    return null;
  }

}
